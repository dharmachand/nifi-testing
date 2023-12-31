set search_path = 'public';

create extension if not exists "uuid-ossp" with schema public;

create table if not exists public.nifi_message_code
(
    id uuid default uuid_generate_v4() not null
    constraint nifi_message_code_pk
    primary key,
    status_code varchar not null,
    default_message varchar not null,
    module_status_code varchar,
    type varchar not null,
    category varchar,
    module_name varchar not null
);