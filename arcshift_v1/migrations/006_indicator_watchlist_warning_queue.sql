CREATE TABLE local_indicator_watchlist (
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    series_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, series_id)
);

CREATE TABLE local_warnings (
    warning_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES fixture_snapshots(snapshot_id),
    data_snapshot_id TEXT NOT NULL REFERENCES local_market_snapshots(snapshot_id),
    title TEXT NOT NULL,
    scenario_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE(signal_id, policy_id)
);

CREATE TABLE local_warning_reviews (
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    warning_id TEXT NOT NULL REFERENCES local_warnings(warning_id),
    review_id TEXT NOT NULL UNIQUE REFERENCES local_reviews(review_id),
    PRIMARY KEY(user_id, warning_id)
);
