CREATE TABLE local_warnings (
    warning_id TEXT PRIMARY KEY,
    event_key TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    fixture_snapshot_id TEXT NOT NULL REFERENCES fixture_snapshots(snapshot_id),
    data_snapshot_id TEXT NOT NULL REFERENCES local_market_snapshots(snapshot_id),
    UNIQUE(event_key, policy_version)
);

ALTER TABLE local_reviews ADD COLUMN warning_id TEXT REFERENCES local_warnings(warning_id);

CREATE UNIQUE INDEX local_reviews_owner_warning ON local_reviews(user_id, warning_id)
    WHERE warning_id IS NOT NULL;

CREATE TABLE local_series_watchlist (
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    series_id TEXT NOT NULL,
    PRIMARY KEY(user_id, series_id)
);
