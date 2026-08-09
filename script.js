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
    let activePointerId = null;
    let pointerOffsetX = 0;
    let pointerOffsetY = 0;
    let pendingLeft = null;
    let pendingTop = null;
    let dragOffsetParent = null;
    let dragVisualOffsetX = 0;
    let dragVisualOffsetY = 0;
    let dragStartClientX = 0;
    let dragStartClientY = 0;
    let hasDragged = false;
    let originalInlinePosition = null;
    let dragFrame = null;

    function clientPositionToParent(clientLeft, clientTop, offsetParent) {
        if (offsetParent === document.documentElement || offsetParent === document.body) {
            return {
                left: clientLeft + window.scrollX,
                top: clientTop + window.scrollY
            };
        }

        const parentRect = offsetParent.getBoundingClientRect();
        return {
            left: clientLeft - parentRect.left - offsetParent.clientLeft + offsetParent.scrollLeft,
            top: clientTop - parentRect.top - offsetParent.clientTop + offsetParent.scrollTop
        };
    }

    function parentPositionToClient(left, top, offsetParent) {
        if (offsetParent === document.documentElement || offsetParent === document.body) {
            return {
                left: left - window.scrollX,
                top: top - window.scrollY
            };
        }

        const parentRect = offsetParent.getBoundingClientRect();
        return {
            left: left + parentRect.left + offsetParent.clientLeft - offsetParent.scrollLeft,
            top: top + parentRect.top + offsetParent.clientTop - offsetParent.scrollTop
        };
    }

    function applyPendingPosition() {
        if (pendingLeft === null || pendingTop === null) return;

        postIt.style.right = 'auto';
        postIt.style.bottom = 'auto';
        postIt.style.left = `${pendingLeft}px`;
        postIt.style.top = `${pendingTop}px`;
    }

    function finishDrag() {
        if (activePointerId === null) return;

        if (dragFrame !== null) {
            cancelAnimationFrame(dragFrame);
            dragFrame = null;
            if (hasDragged) applyPendingPosition();
        }

        if (!hasDragged && originalInlinePosition) {
            postIt.style.left = originalInlinePosition.left;
            postIt.style.top = originalInlinePosition.top;
            postIt.style.right = originalInlinePosition.right;
            postIt.style.bottom = originalInlinePosition.bottom;
        }

        activePointerId = null;
        dragOffsetParent = null;
        dragVisualOffsetX = 0;
        dragVisualOffsetY = 0;
        dragStartClientX = 0;
        dragStartClientY = 0;
        hasDragged = false;
        originalInlinePosition = null;
        pendingLeft = null;
        pendingTop = null;
        postIt.classList.remove('is-dragging');
        postIt.style.removeProperty('--post-it-drag-transform');
    }

    postIt.onpointerdown = event => {
        if (!draggablePostItLayout.matches || activePointerId !== null) return;

        event.preventDefault();

        const postItRect = postIt.getBoundingClientRect();
        const computedStyle = getComputedStyle(postIt);
        originalInlinePosition = {
            left: postIt.style.left,
            top: postIt.style.top,
            right: postIt.style.right,
            bottom: postIt.style.bottom
        };
        dragOffsetParent = postIt.offsetParent || document.documentElement;
        const computedLeft = Number.parseFloat(computedStyle.left);
        const computedTop = Number.parseFloat(computedStyle.top);
        const fallbackPosition = clientPositionToParent(postItRect.left, postItRect.top, dragOffsetParent);
        const lockedPosition = {
            left: Number.isFinite(computedLeft) ? computedLeft : fallbackPosition.left,
            top: Number.isFinite(computedTop) ? computedTop : fallbackPosition.top
        };
        const layoutClientPosition = parentPositionToClient(
            lockedPosition.left,
            lockedPosition.top,
            dragOffsetParent
        );

        dragVisualOffsetX = postItRect.left - layoutClientPosition.left;
        dragVisualOffsetY = postItRect.top - layoutClientPosition.top;

        pointerOffsetX = event.clientX - postItRect.left;
        pointerOffsetY = event.clientY - postItRect.top;
        dragStartClientX = event.clientX;
        dragStartClientY = event.clientY;
        hasDragged = false;
        pendingLeft = lockedPosition.left;
        pendingTop = lockedPosition.top;
        applyPendingPosition();
        postIt.style.setProperty(
            '--post-it-drag-transform',
            computedStyle.transform === 'none' ? 'none' : computedStyle.transform
        );
        postIt.classList.add('is-dragging');
        activePointerId = event.pointerId;
        postIt.setPointerCapture(event.pointerId);
    };

    postIt.onpointermove = event => {
        if (event.pointerId !== activePointerId || !postIt.hasPointerCapture(event.pointerId)) return;

        if (!hasDragged) {
            const movement = Math.hypot(
                event.clientX - dragStartClientX,
                event.clientY - dragStartClientY
            );
            if (movement < 3) return;
            hasDragged = true;
        }

        const postItRect = postIt.getBoundingClientRect();
        const maximumLeft = Math.max(0, window.innerWidth - postItRect.width);
        const maximumTop = Math.max(0, window.innerHeight - postItRect.height);
        const clientLeft = Math.min(Math.max(event.clientX - pointerOffsetX, 0), maximumLeft);
        const clientTop = Math.min(Math.max(event.clientY - pointerOffsetY, 0), maximumTop);
        const nextPosition = clientPositionToParent(
            clientLeft - dragVisualOffsetX,
            clientTop - dragVisualOffsetY,
            dragOffsetParent
        );

        pendingLeft = nextPosition.left;
        pendingTop = nextPosition.top;

        if (dragFrame !== null) return;
        dragFrame = requestAnimationFrame(() => {
            applyPendingPosition();
            dragFrame = null;
        });
    };

    postIt.onpointerup = event => {
        if (event.pointerId !== activePointerId) return;

        finishDrag();
        if (postIt.hasPointerCapture(event.pointerId)) postIt.releasePointerCapture(event.pointerId);
    };

    postIt.onpointercancel = finishDrag;
    postIt.onlostpointercapture = finishDrag;
});
