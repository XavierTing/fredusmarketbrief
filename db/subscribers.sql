-- Applied once in the Supabase SQL editor. Kept here for repo record / re-provisioning.
create table if not exists subscribers (
  id uuid primary key default gen_random_uuid(),
  chat_id bigint unique not null,
  first_name text,
  last_name text,
  username text,
  start_payload text,
  subscribed_at timestamptz not null default now(),
  unsubscribed_at timestamptz,
  active boolean not null default true
);

alter table subscribers enable row level security;
-- No policies: only the server-side service key (which bypasses RLS) may access.
