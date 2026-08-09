# Wave counter setup

The `portfolio website` Supabase project is connected and the
`migrations/001_create_wave_log.sql` migration has been applied. The project URL
and publishable browser key are configured in `../supabase-config.js`.

Each successful click creates one row in `wave_clicks`. The `register_wave`
database function serializes requests per browser UUID and enforces a one-hour
cooldown before inserting, so rapid or concurrent clicks do not create extra
rows. It also records the request IP address, user agent, browser, device type,
platform, and screen size. Raw click rows are not readable or writable through
the public API.

The browser UUID is stored in local storage. Clearing site data or changing
browsers creates a new ID. For a person-level limit across browsers and devices,
replace the browser UUID with Supabase Auth and use `auth.uid()` in the function.
