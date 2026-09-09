-- MergeCash BigQuery Tables
-- All tables in yotam-395120.peerplay dataset

-- 1. Users table — stores signup + player link info
CREATE TABLE IF NOT EXISTS `yotam-395120.peerplay.mergecash_users` (
  user_id STRING NOT NULL,           -- UUID generated at signup
  email STRING NOT NULL,
  player_id STRING,                   -- linked after signup (24-char hex)
  segment STRING,                     -- assigned after player_id link based on BQ data
  signup_ip STRING,
  status STRING DEFAULT 'active',     -- active | fraud_flagged | completed | expired
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  player_id_linked_at TIMESTAMP,
  offer_expires_at TIMESTAMP,         -- set when player_id linked (14 days from link)
  source_url_params STRING,           -- JSON string of URL params from in-game popup
  device_id STRING                    -- from dim_player, for fraud dedup
);

-- 2. Milestone progress — one row per user per milestone
CREATE TABLE IF NOT EXISTS `yotam-395120.peerplay.mergecash_milestones` (
  user_id STRING NOT NULL,
  player_id STRING NOT NULL,
  milestone_id STRING NOT NULL,       -- e.g. ch115, ch120, ch125, ch130, ch135
  target_chapter INT64 NOT NULL,
  reward_amount FLOAT64 NOT NULL,
  status STRING DEFAULT 'pending',    -- pending | completed
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- 3. Segment configs — defines offer templates per segment
CREATE TABLE IF NOT EXISTS `yotam-395120.peerplay.mergecash_segments` (
  segment_id STRING NOT NULL,
  name STRING NOT NULL,
  description STRING,
  milestones STRING NOT NULL,         -- JSON array: [{"id":"ch115","chapter":115,"reward":5.00}, ...]
  total_reward FLOAT64 NOT NULL,
  reward_type STRING DEFAULT 'amazon_gift_card',
  time_limit_days INT64 DEFAULT 14,
  is_active BOOL DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- 4. Events table — funnel tracking (partitioned, small + fast)
CREATE TABLE IF NOT EXISTS `yotam-395120.peerplay.mergecash_events` (
  event_timestamp TIMESTAMP NOT NULL,
  event_name STRING NOT NULL,         -- signup | login | player_id_linked | milestone_completed | all_milestones_completed | reward_requested | page_view
  user_id STRING,
  player_id STRING,
  email STRING,
  segment STRING,
  properties STRING                   -- JSON string for extra data
)
PARTITION BY DATE(event_timestamp)
OPTIONS (
  partition_expiration_days = 365
);

-- 5. Rewards table — tracks gift card fulfillment
CREATE TABLE IF NOT EXISTS `yotam-395120.peerplay.mergecash_rewards` (
  reward_id STRING NOT NULL,          -- UUID
  user_id STRING NOT NULL,
  player_id STRING NOT NULL,
  email STRING NOT NULL,
  segment STRING,
  reward_type STRING DEFAULT 'amazon_gift_card',
  reward_amount FLOAT64 NOT NULL,
  status STRING DEFAULT 'pending_approval',  -- pending_approval | fulfilled | denied
  admin_notes STRING,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  fulfilled_at TIMESTAMP
);
