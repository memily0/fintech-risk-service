CREATE TABLE local_password_resets (
    user_id TEXT PRIMARY KEY REFERENCES local_users(user_id),
    token_hash TEXT NOT NULL UNIQUE CHECK(length(token_hash) = 64),
    expires_at INTEGER NOT NULL
);

CREATE TABLE local_password_reset_outbox (
    token_hash TEXT PRIMARY KEY REFERENCES local_password_resets(token_hash) ON DELETE CASCADE,
    token TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
