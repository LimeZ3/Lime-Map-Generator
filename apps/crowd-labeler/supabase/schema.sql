create table if not exists public.maps (
  id uuid primary key default gen_random_uuid(),
  map_dir text not null unique,
  canonical_name text not null,
  version text,
  size_x integer,
  size_z integer,
  player_count integer,
  inventory_source text,
  preview_url text,
  structural_preview_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.respondents (
  id uuid primary key default gen_random_uuid(),
  anonymous_key_hash text not null unique,
  display_name text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create table if not exists public.question_definitions (
  id uuid primary key default gen_random_uuid(),
  key text not null unique,
  prompt text not null,
  question_type text not null check (question_type in ('scale', 'multi_choice', 'single_choice', 'text')),
  scale_min integer,
  scale_max integer,
  active boolean not null default true,
  category text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.responses (
  id uuid primary key default gen_random_uuid(),
  map_id uuid not null references public.maps(id),
  respondent_id uuid not null references public.respondents(id),
  question_id uuid not null references public.question_definitions(id),
  numeric_value numeric,
  choice_values text[] not null default '{}',
  text_value text,
  unknown boolean not null default false,
  familiarity text not null check (
    familiarity in ('never_played', 'seen_it', 'played_casually', 'know_it_well')
  ),
  client_session_id text not null,
  created_at timestamptz not null default now()
);

create unique index if not exists responses_one_current_answer
  on public.responses (map_id, respondent_id, question_id);

create or replace view public.aggregated_map_labels as
with numeric_responses as (
  select
    responses.map_id,
    question_definitions.key as question_key,
    responses.numeric_value,
    responses.unknown,
    case responses.familiarity
      when 'never_played' then 0.5
      when 'seen_it' then 0.75
      when 'played_casually' then 1.0
      when 'know_it_well' then 1.5
      else 1.0
    end as familiarity_weight
  from public.responses
  join public.question_definitions on question_definitions.id = responses.question_id
  where question_definitions.question_type = 'scale'
)
select
  map_id,
  question_key,
  count(numeric_value) filter (where not unknown) as response_count,
  avg(numeric_value) filter (where not unknown) as mean,
  percentile_cont(0.5) within group (order by numeric_value) filter (where not unknown) as median,
  stddev_samp(numeric_value) filter (where not unknown) as stddev,
  count(*) filter (where unknown) as unknown_count,
  (
    sum(numeric_value * familiarity_weight) filter (where not unknown)
    / nullif(sum(familiarity_weight) filter (where not unknown), 0)
  ) as weighted_mean,
  now() as updated_at
from numeric_responses
group by map_id, question_key;
