CREATE TABLE local_market_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    synthetic INTEGER NOT NULL CHECK(synthetic = 1),
    imported_at INTEGER NOT NULL
);

CREATE TABLE local_market_active (
    slot INTEGER PRIMARY KEY CHECK(slot = 1),
    snapshot_id TEXT NOT NULL REFERENCES local_market_snapshots(snapshot_id)
);
