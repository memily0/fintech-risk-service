CREATE TABLE local_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0, 1)),
    synthetic INTEGER NOT NULL CHECK(synthetic = 1),
    created_at INTEGER NOT NULL
);

CREATE TABLE local_verification_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    expires_at INTEGER NOT NULL,
    consumed_at INTEGER
);

CREATE TABLE local_sessions (
    session_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    csrf_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER
);

CREATE INDEX local_sessions_user ON local_sessions(user_id);

CREATE TABLE local_dev_outbox (
    message_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    token_hash TEXT NOT NULL REFERENCES local_verification_tokens(token_hash),
    purpose TEXT NOT NULL CHECK(purpose = 'verify_email'),
    token TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE local_auth_rate_limits (
    bucket_key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    attempts INTEGER NOT NULL CHECK(attempts >= 0)
);

CREATE TABLE local_auth_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES local_users(user_id),
    event TEXT NOT NULL CHECK(event IN ('registered', 'verified', 'login', 'logout')),
    occurred_at INTEGER NOT NULL
);
