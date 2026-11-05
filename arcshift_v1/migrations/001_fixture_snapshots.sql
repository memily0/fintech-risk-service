CREATE TABLE fixture_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    fixture_version TEXT NOT NULL UNIQUE,
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    payload_json TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK(synthetic = 1),
    imported_at TEXT NOT NULL
);

CREATE TABLE fixture_active_snapshot (
    slot INTEGER PRIMARY KEY CHECK(slot = 1),
    snapshot_id TEXT NOT NULL REFERENCES fixture_snapshots(snapshot_id)
);
