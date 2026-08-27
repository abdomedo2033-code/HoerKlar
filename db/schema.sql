-- Supabase Postgres schema — see docs/REPORT.md §G for commentary
create extension if not exists pgcrypto;
create type rights_status as enum ('PUBLIC_DOMAIN','CC0','CC_BY','CC_BY_SA','CC_BY_NC','CC_BY_NC_SA','CC_BY_ND','CC_BY_NC_ND','PLATFORM_ONLY','EMBED_ONLY','LICENSE_REQUIRED','UNKNOWN');
create type video_status as enum ('ACTIVE','TEMPORARILY_UNAVAILABLE','REMOVED','LICENSE_CHANGED','EMBED_DISABLED');
create table providers(id uuid primary key default gen_random_uuid(), name text unique not null, type text not null, api_url text, documentation_url text, supports_streaming bool, supports_timestamp bool, supports_embedding bool, active bool default true);
insert into providers(name,type,api_url,supports_streaming,supports_timestamp,supports_embedding) values
('open_beelden','oai-pmh','https://www.openbeelden.nl/feeds/oai/',true,true,true),
('wikimedia','mediawiki','https://commons.wikimedia.org/w/api.php',true,true,true),
('youtube','iframe','https://www.googleapis.com/youtube/v3',true,true,true),
('vimeo','player-sdk','https://api.vimeo.com',true,true,true),
('internet_archive','s3','https://archive.org/metadata/',true,true,true),
('europeana','search','https://api.europeana.eu/record/v2',false,false,false),
('peertube','rest','https://search.joinpeertube.org/api/v1/search/videos',true,true,true);
create table videos(id uuid primary key default gen_random_uuid(), provider_id uuid references providers(id), external_id text not null, title text, description text, language text, duration float, thumbnail_url text, source_url text, embed_url text, license text, license_url text, creator text, attribution text, rights_status rights_status not null default 'UNKNOWN', rights_checked_at timestamptz, rights_checked_by text, source_terms_url text, status video_status default 'ACTIVE', approved bool default false, last_verified_at timestamptz, unique(provider_id, external_id));
create table clips(id uuid primary key default gen_random_uuid(), video_id uuid references videos(id) on delete cascade, start_time double precision not null, end_time double precision not null, dutch_text text not null, translation text, cefr text check(cefr in ('A1','A2','B1','B2','C1','C2')), difficulty float, quality_score float, recommended bool, approved bool default false, check(end_time>start_time and end_time-start_time between 2 and 15));
create table questions(id uuid primary key default gen_random_uuid(), clip_id uuid references clips(id) on delete cascade, type text check(type in ('translation','listening','recognition','cloze','vocab','grammar','dictation')), question text not null, correct_answer text not null);
create table question_options(id uuid primary key default gen_random_uuid(), question_id uuid references questions(id) on delete cascade, text text not null, is_correct bool not null);
create table attempts(id uuid primary key default gen_random_uuid(), user_id uuid, clip_id uuid references clips(id), question_id uuid references questions(id), answer text, correct bool, response_time int, created_at timestamptz default now());
