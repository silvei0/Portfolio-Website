# Portfolio Supabase tracking

The `portfolio website` Supabase project is connected. The project URL and
publishable browser key are configured in `../supabase-config.js`.

## Wave clicks

Each successful click creates one row in `wave_clicks`. The `register_wave`
database function serializes requests per browser UUID and enforces a one-hour
cooldown before inserting, so rapid or concurrent clicks do not create extra
rows. It also records the request IP address, user agent, browser, device type,
platform, and screen size. Raw click rows are not readable or writable through
the public API.

The browser UUID is stored in local storage. Clearing site data or changing
browsers creates a new ID. For a person-level limit across browsers and devices,
replace the browser UUID with Supabase Auth and use `auth.uid()` in the function.

## Anonymous site traffic

The `003_create_site_traffic.sql` migration creates the private `site_visits`
table and the public, rate-limited `register_site_visit` submission function.
Every public page loads `traffic.js`, which records:

- Visit time, page path and page title
- Referring domain (not the full referring URL)
- Request IP address and user agent
- Browser, device type, platform, screen and viewport sizes
- Browser language and timezone

The browser does not receive read access to traffic rows. It can only call the
constrained submission function. Repeated loads of the same page from the same
IP within 30 seconds are ignored, and each IP is limited to 60 accepted visits
per minute. Local development, Global Privacy Control and Do Not Track are
excluded. Unlike wave clicks, ordinary visits do not create a persistent browser
identifier.

Useful private queries in the Supabase SQL Editor:

```sql
-- Visits by day
select date_trunc('day', visited_at) as day, count(*) as visits
from public.site_visits
group by 1
order by 1 desc;

-- Most-viewed pages
select page_path, count(*) as visits
from public.site_visits
group by page_path
order by visits desc;

-- Device and browser breakdown
select device_type, browser, count(*) as visits
from public.site_visits
group by device_type, browser
order by visits desc;
```

Because request IP addresses and user agents can be personal data, explain this
tracking in the site's privacy notice before treating the analytics as
production-ready.
