alter table public.wave_clicks
    add column if not exists ip_address inet,
    add column if not exists browser text,
    add column if not exists device_type text,
    add column if not exists platform text,
    add column if not exists screen_size text,
    add column if not exists user_agent text;

drop function if exists public.register_wave(uuid);

create function public.register_wave(
    p_user_id uuid,
    p_browser text,
    p_device_type text,
    p_platform text,
    p_screen_size text
)
returns table (
    accepted boolean,
    total_count bigint,
    retry_after_seconds integer
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    v_last_wave timestamptz;
    v_headers jsonb := coalesce(current_setting('request.headers', true), '{}')::jsonb;
    v_ip_address inet;
    v_user_agent text;
begin
    begin
        v_ip_address := nullif(trim(split_part(v_headers->>'x-forwarded-for', ',', 1)), '')::inet;
    exception when invalid_text_representation then
        v_ip_address := null;
    end;

    v_user_agent := left(coalesce(v_headers->>'user-agent', 'Unknown'), 500);

    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    select wc.created_at
      into v_last_wave
      from public.wave_clicks as wc
     where wc.user_id = p_user_id
     order by wc.created_at desc
     limit 1;

    if v_last_wave is not null and v_last_wave > now() - interval '1 hour' then
        return query
        select
            false,
            (select count(*) from public.wave_clicks),
            greatest(
                1,
                ceil(extract(epoch from ((v_last_wave + interval '1 hour') - now())))::integer
            );
        return;
    end if;

    insert into public.wave_clicks (
        user_id,
        ip_address,
        browser,
        device_type,
        platform,
        screen_size,
        user_agent
    ) values (
        p_user_id,
        v_ip_address,
        left(coalesce(p_browser, 'Unknown'), 80),
        left(coalesce(p_device_type, 'Unknown'), 40),
        left(coalesce(p_platform, 'Unknown'), 100),
        left(coalesce(p_screen_size, 'Unknown'), 30),
        v_user_agent
    );

    return query
    select true, (select count(*) from public.wave_clicks), 0;
end;
$$;

revoke all on function public.register_wave(uuid, text, text, text, text) from public;
revoke all on function public.register_wave(uuid, text, text, text, text) from authenticated;
grant execute on function public.register_wave(uuid, text, text, text, text) to anon;
