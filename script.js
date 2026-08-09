const sayHiButton = document.querySelector('.say-hi');
const sayHiStatus = document.querySelector('.say-hi-status');

const statusBubble = document.querySelector('[data-status-bubble]');
const statusText = statusBubble?.querySelector('.thought-bubble-status');
const DEFAULT_PORTFOLIO_STATUS = 'No specific thoughts right now...';
const STATUS_REFRESH_INTERVAL = 60_000;
let statusExpiryTimer = null;

function showPortfolioStatus(value, isInactive = false) {
    if (!statusText) return;

    const status = typeof value === 'string' ? value.trim() : '';
    statusText.textContent = status;
    statusText.hidden = !status;
    statusText.classList.toggle('thought-bubble-status--inactive', Boolean(status) && isInactive);
}

function scheduleStatusExpiry(expiresAt, defaultStatus) {
    window.clearTimeout(statusExpiryTimer);

    const remaining = expiresAt - Date.now();
    if (remaining <= 0) {
        showPortfolioStatus(defaultStatus, true);
        return;
    }

    const maximumDelay = 2_147_000_000;
    statusExpiryTimer = window.setTimeout(() => {
        if (expiresAt > Date.now()) scheduleStatusExpiry(expiresAt, defaultStatus);
        else showPortfolioStatus(defaultStatus, true);
    }, Math.min(remaining, maximumDelay));
}

async function refreshPortfolioStatus() {
    if (!statusBubble || !statusText) return;

    const source = statusBubble.dataset.statusSource || '../status.json';

    try {
        const response = await fetch(source, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Status request failed: ${response.status}`);

        const data = await response.json();
        const defaultStatus = typeof data.defaultStatus === 'string'
            ? data.defaultStatus.trim()
            : DEFAULT_PORTFOLIO_STATUS;
        const status = typeof data.status === 'string' ? data.status.trim() : '';
        const expiresAt = Date.parse(data.expiresAt);
        const isActive = status && Number.isFinite(expiresAt) && expiresAt > Date.now();

        showPortfolioStatus(isActive ? status : defaultStatus, !isActive);

        if (isActive) scheduleStatusExpiry(expiresAt, defaultStatus);
        else window.clearTimeout(statusExpiryTimer);
    } catch (error) {
        console.warn('Portfolio status could not be loaded.', error);
        window.clearTimeout(statusExpiryTimer);
        showPortfolioStatus(DEFAULT_PORTFOLIO_STATUS, true);
    }
}

if (statusBubble && statusText) {
    refreshPortfolioStatus();
    window.setInterval(refreshPortfolioStatus, STATUS_REFRESH_INTERVAL);
}

if (sayHiButton && sayHiStatus) {
    sayHiButton.addEventListener('click', async () => {
        if (sayHiButton.disabled) return;

        const config = window.SUPABASE_CONFIG;

        if (!config?.url || !config?.publishableKey) {
            sayHiStatus.textContent = 'Wave setup needed.';
            return;
        }

        sayHiButton.disabled = true;
        sayHiStatus.textContent = 'Sending...';

        try {
            const userId = getWaveUserId();
            const visitorInfo = getVisitorInfo();
            const response = await fetch(`${config.url}/rest/v1/rpc/register_wave`, {
                method: 'POST',
                headers: {
                    apikey: config.publishableKey,
                    Authorization: `Bearer ${config.publishableKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    p_user_id: userId,
                    p_browser: visitorInfo.browser,
                    p_device_type: visitorInfo.deviceType,
                    p_platform: visitorInfo.platform,
                    p_screen_size: visitorInfo.screenSize
                })
            });

            if (!response.ok) throw new Error(`Wave request failed: ${response.status}`);

            const [result] = await response.json();

            if (!result?.accepted) {
                const minutes = Math.max(1, Math.ceil(result.retry_after_seconds / 60));
                sayHiStatus.textContent = `Wave again in ${minutes}m.`;
                return;
            }

            sayHiButton.classList.add('clicked');
            sayHiButton.setAttribute('aria-pressed', 'true');
            sayHiStatus.textContent = 'Hi sent!';
        } catch (error) {
            console.error(error);
            sayHiButton.disabled = false;
            sayHiStatus.textContent = 'Could not send. Try again.';
        }
    });
}

function getWaveUserId() {
    const storageKey = 'fiza_wave_user_id';
    let userId = localStorage.getItem(storageKey);

    if (!userId) {
        userId = crypto.randomUUID();
        localStorage.setItem(storageKey, userId);
    }

    return userId;
}

function getVisitorInfo() {
    const userAgent = navigator.userAgent;
    let browser = 'Other';

    if (/Edg\//.test(userAgent)) browser = 'Edge';
    else if (/OPR\//.test(userAgent)) browser = 'Opera';
    else if (/Chrome\//.test(userAgent)) browser = 'Chrome';
    else if (/Firefox\//.test(userAgent)) browser = 'Firefox';
    else if (/Safari\//.test(userAgent)) browser = 'Safari';

    let deviceType = 'Desktop';
    if (/iPad|Tablet/i.test(userAgent)) deviceType = 'Tablet';
    else if (/Mobi|Android|iPhone/i.test(userAgent)) deviceType = 'Mobile';

    return {
        browser,
        deviceType,
        platform: navigator.userAgentData?.platform || navigator.platform || 'Unknown',
        screenSize: `${window.screen.width}x${window.screen.height}`
    };
}

const draggablePostItLayout = window.matchMedia('(min-width: 901px) and (pointer: fine)');

document.querySelectorAll('.post-it').forEach(postIt => {
    let pointerOffsetX;
    let pointerOffsetY;
    let pendingLeft;
    let pendingTop;
    let dragFrame = null;

    postIt.onpointerdown = event => {
        if (!draggablePostItLayout.matches) return;

        const postItRect = postIt.getBoundingClientRect();
        pointerOffsetX = event.clientX - postItRect.left;
        pointerOffsetY = event.clientY - postItRect.top;
        postIt.setPointerCapture(event.pointerId);
    };

    postIt.onpointermove = event => {
        if (!postIt.hasPointerCapture(event.pointerId)) return;

        const offsetParent = postIt.offsetParent || document.documentElement;
        const parentRect = offsetParent.getBoundingClientRect();
        const maximumLeft = Math.max(0, window.innerWidth - postIt.offsetWidth);
        const maximumTop = Math.max(0, window.innerHeight - postIt.offsetHeight);
        const clientLeft = Math.min(Math.max(event.clientX - pointerOffsetX, 0), maximumLeft);
        const clientTop = Math.min(Math.max(event.clientY - pointerOffsetY, 0), maximumTop);

        pendingLeft = clientLeft - parentRect.left + offsetParent.scrollLeft;
        pendingTop = clientTop - parentRect.top + offsetParent.scrollTop;

        if (dragFrame !== null) return;
        dragFrame = requestAnimationFrame(() => {
            postIt.style.right = 'auto';
            postIt.style.bottom = 'auto';
            postIt.style.left = `${pendingLeft}px`;
            postIt.style.top = `${pendingTop}px`;
            dragFrame = null;
        });
    };

    postIt.onpointercancel = () => {
        if (dragFrame !== null) cancelAnimationFrame(dragFrame);
        dragFrame = null;
    };
});
