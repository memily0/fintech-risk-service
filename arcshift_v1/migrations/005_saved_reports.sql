CREATE TABLE local_saved_reports (
    report_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    review_id TEXT NOT NULL REFERENCES local_reviews(review_id),
    data_snapshot_id TEXT NOT NULL REFERENCES local_market_snapshots(snapshot_id),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    created_at INTEGER NOT NULL
);

CREATE INDEX local_saved_reports_owner ON local_saved_reports(user_id, created_at, report_id);
