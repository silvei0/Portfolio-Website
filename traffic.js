(() => {
    const config = window.SUPABASE_CONFIG;
    const localHosts = new Set(['localhost', '127.0.0.1', '::1']);

    if (!config?.url || !config?.publishableKey) return;
    if (localHosts.has(window.location.hostname) || window.location.protocol === 'file:') return;
    if (navigator.globalPrivacyControl === true || navigator.doNotTrack === '1') return;

    function getBrowserDetails() {
        const userAgent = navigator.userAgent;
        let browser = 'Other';

        if (/Edg\//.test(userAgent)) browser = 'Edge';
        else if (/OPR\//.test(userAgent)) browser = 'Opera';
        else if (/SamsungBrowser\//.test(userAgent)) browser = 'Samsung Internet';
        else if (/Chrome\//.test(userAgent)) browser = 'Chrome';
        else if (/Firefox\//.test(userAgent)) browser = 'Firefox';
        else if (/Safari\//.test(userAgent)) browser = 'Safari';

        let deviceType = 'Desktop';
        const isTablet = /iPad|Tablet/i.test(userAgent)
            || (/Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1);

        if (isTablet) deviceType = 'Tablet';
        else if (/Mobi|Android|iPhone/i.test(userAgent)) deviceType = 'Mobile';

        return { browser, deviceType };
    }

    function getPagePath() {
        const scriptPath = new URL(document.currentScript?.src || window.location.href).pathname;
        const siteRoot = scriptPath.endsWith('/traffic.js')
            ? scriptPath.slice(0, -'/traffic.js'.length)
            : '';
        let pagePath = window.location.pathname;

        if (siteRoot && siteRoot !== '/' && (pagePath === siteRoot || pagePath.startsWith(`${siteRoot}/`))) {
            pagePath = pagePath.slice(siteRoot.length) || '/';
        }

        return pagePath.replace(/index\.html$/i, '') || '/';
    }

    function getReferrerHost() {
        if (!document.referrer) return null;

        try {
            const referrer = new URL(document.referrer);
            return referrer.host === window.location.host ? 'internal' : referrer.hostname;
        } catch {
            return null;
        }
    }

    async function recordPageVisit() {
        const { browser, deviceType } = getBrowserDetails();
        const payload = {
            p_page_path: getPagePath(),
            p_page_title: document.title,
            p_referrer_host: getReferrerHost(),
            p_browser: browser,
            p_device_type: deviceType,
            p_platform: navigator.userAgentData?.platform || navigator.platform || 'Unknown',
            p_screen_size: `${window.screen.width}x${window.screen.height}`,
            p_viewport_size: `${window.innerWidth}x${window.innerHeight}`,
            p_language: navigator.language || 'Unknown',
            p_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Unknown'
        };

        try {
            const response = await fetch(`${config.url}/rest/v1/rpc/register_site_visit`, {
                method: 'POST',
                headers: {
                    apikey: config.publishableKey,
                    Authorization: `Bearer ${config.publishableKey}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload),
                keepalive: true
            });

            if (!response.ok) throw new Error(`Traffic request failed: ${response.status}`);
        } catch (error) {
            console.warn('Anonymous site traffic could not be recorded.', error);
        }
    }

    if ('requestIdleCallback' in window) {
        window.requestIdleCallback(recordPageVisit, { timeout: 2000 });
    } else {
        window.setTimeout(recordPageVisit, 0);
    }
})();
