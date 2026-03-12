-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ─────────────────────────────────────────
-- CORE
-- ─────────────────────────────────────────

create table topics (
  id            uuid primary key default uuid_generate_v4(),
  name          text not null unique,
  canonical_name text not null,
  first_seen    date not null default current_date,
  created_at    timestamptz not null default now()
);

create table daily_runs (
  id             uuid primary key default uuid_generate_v4(),
  run_date       date not null unique,
  status         text not null default 'running',  -- running | complete | failed
  topics_scored  int default 0,
  created_at     timestamptz not null default now()
);

-- ─────────────────────────────────────────
-- SIGNAL DATA
-- ─────────────────────────────────────────

create table topic_signals (
  id               uuid primary key default uuid_generate_v4(),
  run_id           uuid not null references daily_runs(id) on delete cascade,
  topic_id         uuid not null references topics(id) on delete cascade,
  signal_source    text not null,   -- wikipedia, reddit, google_trends, etc.
  signal_category  text not null,   -- media | demand | behavior | builder | community | money
  raw_value        numeric,
  baseline_value   numeric,
  spike_score      numeric,         -- (raw - baseline) / baseline
  fired            boolean not null default false,
  created_at       timestamptz not null default now()
);

create index on topic_signals(run_id);
create index on topic_signals(topic_id);

-- ─────────────────────────────────────────
-- SCORES
-- ─────────────────────────────────────────

create table topic_scores (
  id                      uuid primary key default uuid_generate_v4(),
  run_id                  uuid not null references daily_runs(id) on delete cascade,
  topic_id                uuid not null references topics(id) on delete cascade,
  independence_score      numeric,  -- unique categories fired / 6
  persistence_score       numeric,  -- days above baseline (normalized 0-1)
  velocity_score          numeric,  -- rate of acceleration
  frustration_score       numeric,  -- negative sentiment proxy
  supply_gap_score        numeric,  -- thin supply proxy
  demand_score            numeric,  -- organic demand strength
  opportunity_score       numeric,  -- composite final score
  timeline_position       text,     -- EMERGING | CRYSTALLIZING | MAINSTREAM | PEAKING | DECLINING
  vocabulary_fragmentation numeric, -- unmapped category signal
  lead_indicator_ratio    numeric,  -- builder signals / total signals
  categories_fired        text[],   -- which categories fired
  sources_fired           text[],   -- which individual sources fired
  created_at              timestamptz not null default now()
);

create index on topic_scores(run_id);
create index on topic_scores(opportunity_score desc);

-- ─────────────────────────────────────────
-- AI SYNTHESIS
-- ─────────────────────────────────────────

create table topic_syntheses (
  id                     uuid primary key default uuid_generate_v4(),
  run_id                 uuid not null references daily_runs(id) on delete cascade,
  topic_id               uuid not null references topics(id) on delete cascade,
  gap_analysis           text,
  opportunity_brief      text,
  historical_pattern_match text,
  what_to_watch          text,
  app_fit_score          numeric,
  app_concept            text,
  created_at             timestamptz not null default now()
);

-- ─────────────────────────────────────────
-- SELF-REFLECTION
-- ─────────────────────────────────────────

create table recommendations (
  id                  uuid primary key default uuid_generate_v4(),
  run_id              uuid not null references daily_runs(id),
  topic_id            uuid not null references topics(id),
  recommendation_date date not null default current_date,
  confidence_score    numeric,
  opportunity_brief   text,
  created_at          timestamptz not null default now()
);

create table outcomes (
  id                 uuid primary key default uuid_generate_v4(),
  recommendation_id  uuid not null references recommendations(id),
  outcome_date       date,
  outcome_type       text,  -- REAL_MARKET | FIZZLED | EMERGING | MISSED
  evidence           text,
  user_note          text,
  auto_detected      boolean default false,
  created_at         timestamptz not null default now()
);

create table signal_performance (
  id                uuid primary key default uuid_generate_v4(),
  signal_source     text not null,
  domain            text default 'all',
  true_positives    int default 0,
  false_positives   int default 0,
  true_negatives    int default 0,
  false_negatives   int default 0,
  precision         numeric,
  recall            numeric,
  avg_lead_time_days numeric,
  updated_at        timestamptz not null default now(),
  unique(signal_source, domain)
);

create table institutional_knowledge (
  id                   uuid primary key default uuid_generate_v4(),
  version              int not null,
  knowledge_brief      text not null,
  performance_summary  text,
  created_at           timestamptz not null default now()
);

-- ─────────────────────────────────────────
-- USER
-- ─────────────────────────────────────────

create table user_thesis (
  id             uuid primary key default uuid_generate_v4(),
  build_profile  text,
  domains        text[],
  skills         text[],
  past_projects  text,
  avoid_domains  text[],
  updated_at     timestamptz not null default now()
);

create table saved_opportunities (
  id         uuid primary key default uuid_generate_v4(),
  topic_id   uuid not null references topics(id),
  user_note  text,
  created_at timestamptz not null default now()
);

-- ─────────────────────────────────────────
-- APP PROJECTS (Agentic Build Framework)
-- ─────────────────────────────────────────

create table app_projects (
  id                   uuid primary key default uuid_generate_v4(),
  name                 text not null,
  opportunity_topic_id uuid references topics(id),
  status               text not null default 'IDEATING',
  -- IDEATING | BUILDING | SUBMITTED | LIVE | PAUSED
  platform             text default 'ios_android',
  repo_url             text,
  app_store_id         text,
  play_store_id        text,
  bundle_id            text,
  created_at           timestamptz not null default now()
);

create table app_builds (
  id             uuid primary key default uuid_generate_v4(),
  project_id     uuid not null references app_projects(id) on delete cascade,
  build_date     date not null default current_date,
  eas_build_id   text,
  platform       text,  -- ios | android | all
  status         text,  -- building | finished | errored | submitted | approved | rejected
  submitted_at   timestamptz,
  approved_at    timestamptz,
  rejection_reason text,
  created_at     timestamptz not null default now()
);

create table app_revenue (
  id              uuid primary key default uuid_generate_v4(),
  project_id      uuid not null references app_projects(id) on delete cascade,
  date            date not null default current_date,
  free_users      int default 0,
  paid_users      int default 0,
  mrr             numeric default 0,
  revenuecat_data jsonb,
  created_at      timestamptz not null default now(),
  unique(project_id, date)
);

create table app_tasks (
  id               uuid primary key default uuid_generate_v4(),
  project_id       uuid not null references app_projects(id) on delete cascade,
  task_description text not null,
  generated_code   text,
  file_path        text,
  status           text not null default 'PENDING',
  -- PENDING | IN_PROGRESS | APPROVED | COMMITTED
  user_approved    boolean default false,
  created_at       timestamptz not null default now()
);

-- Seed default signal performance rows (one per source)
insert into signal_performance (signal_source, domain, true_positives, false_positives, true_negatives, false_negatives)
values
  ('wikipedia', 'all', 0, 0, 0, 0),
  ('reddit', 'all', 0, 0, 0, 0),
  ('google_trends', 'all', 0, 0, 0, 0),
  ('gdelt', 'all', 0, 0, 0, 0),
  ('youtube', 'all', 0, 0, 0, 0),
  ('github_trending', 'all', 0, 0, 0, 0),
  ('arxiv', 'all', 0, 0, 0, 0),
  ('itunes', 'all', 0, 0, 0, 0),
  ('producthunt', 'all', 0, 0, 0, 0),
  ('markets', 'all', 0, 0, 0, 0),
  ('app_store', 'all', 0, 0, 0, 0),
  ('kickstarter', 'all', 0, 0, 0, 0),
  ('amazon_movers', 'all', 0, 0, 0, 0),
  ('discord', 'all', 0, 0, 0, 0),
  ('uspto', 'all', 0, 0, 0, 0),
  ('sbir', 'all', 0, 0, 0, 0),
  ('stackoverflow', 'all', 0, 0, 0, 0),
  ('substack', 'all', 0, 0, 0, 0),
  ('federal_register', 'all', 0, 0, 0, 0),
  ('job_postings', 'all', 0, 0, 0, 0),
  ('crunchbase', 'all', 0, 0, 0, 0),
  ('xiaohongshu', 'all', 0, 0, 0, 0);
