CREATE TABLE local_watchlist (
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    scenario_id TEXT NOT NULL CHECK(scenario_id IN ('loading', 'empty', 'stale', 'unsupported', 'error', 'historical_demo')),
    created_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, scenario_id)
);

CREATE TABLE local_reviews (
    review_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    snapshot_id TEXT NOT NULL REFERENCES fixture_snapshots(snapshot_id),
    scenario_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('acknowledged', 'in_review', 'closed', 'dismissed')),
    note TEXT NOT NULL CHECK(length(note) <= 4000),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE INDEX local_reviews_owner ON local_reviews(user_id, created_at, review_id);

CREATE TABLE local_review_events (
    event_id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES local_reviews(review_id),
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    status TEXT NOT NULL CHECK(status IN ('acknowledged', 'in_review', 'closed', 'dismissed')),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    occurred_at INTEGER NOT NULL,
    UNIQUE(review_id, revision)
);
