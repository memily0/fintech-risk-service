"""Local .test identities only. No real email delivery or production auth."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import hmac
from pathlib import Path
import secrets
import string
import time
from typing import Callable
import uuid

from email_validator import validate_email
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from .database import check_schema, connect


SESSION_COOKIE = "arcshift_dev_session"
CSRF_COOKIE = "arcshift_dev_csrf"
TOKEN_CHARACTERS = frozenset(string.ascii_letters + string.digits + "_-")


class AuthFailure(Exception):
    def __init__(self, code: str, status: int = 401):
        self.code = code
        self.status = status


def normalize_test_email(value: str) -> str:
    normalized = validate_email(value, check_deliverability=False, test_environment=True, allow_smtputf8=False).normalized.casefold()
    if not normalized.rsplit("@", 1)[1].endswith(".test"):
        raise ValueError("Only synthetic .test email domains are enabled")
    return normalized


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def valid_token(value) -> bool:
    return isinstance(value, str) and 32 <= len(value) <= 128 and all(char in TOKEN_CHARACTERS for char in value)


@lru_cache(maxsize=1)
def password_hasher():
    return PasswordHash.recommended()


@lru_cache(maxsize=1)
def dummy_hash():
    return password_hasher().hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class AuthPolicy:
    verification_seconds: int = 900
    session_seconds: int = 3600
    rate_window_seconds: int = 60
    rate_limit: int = 10

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in (self.verification_seconds, self.session_seconds, self.rate_window_seconds, self.rate_limit)):
            raise ValueError("Local auth policy values must be positive integers")


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    email: str
    created_at: int
    csrf_hash: str


class AuthService:
    def __init__(self, path: Path, policy: AuthPolicy | None = None, clock: Callable[[], float] = time.time):
        self.path = path
        self.policy = AuthPolicy() if policy is None else policy
        self.clock = clock
        check_schema(path)
        dummy_hash()

    @contextmanager
    def transaction(self):
        check_schema(self.path)
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def check_ready(self):
        check_schema(self.path)
        with closing(connect(self.path, readonly=True)) as connection:
            connection.execute("SELECT user_id FROM local_users LIMIT 1").fetchall()

    def _rate_limit(self, action, peer, email=None):
        now = int(self.clock())
        start = now - now % self.policy.rate_window_seconds
        keys = [action + ":ip:" + digest(peer)]
        if email is not None:
            keys.append(action + ":identity:" + digest(email))
        with self.transaction() as connection:
            for key in keys:
                row = connection.execute("SELECT window_start, attempts FROM local_auth_rate_limits WHERE bucket_key=?", (key,)).fetchone()
                if row is not None and row["window_start"] == start and row["attempts"] >= self.policy.rate_limit:
                    raise AuthFailure("auth_rate_limited", 429)
            for key in keys:
                connection.execute(
                    "INSERT INTO local_auth_rate_limits VALUES (?, ?, 1) ON CONFLICT(bucket_key) DO UPDATE SET window_start=excluded.window_start, attempts=CASE WHEN window_start=excluded.window_start THEN attempts+1 ELSE 1 END",
                    (key, start),
                )

    @staticmethod
    def _event(connection, user_id, event, now):
        connection.execute("INSERT INTO local_auth_events VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), user_id, event, now))

    def register(self, email, password, peer):
        email = normalize_test_email(email)
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise ValueError("Password must contain 15 to 128 characters")
        self._rate_limit("register", peer, email)
        encoded = password_hasher().hash(password)
        now = int(self.clock())
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM local_users WHERE email=?", (email,)).fetchone() is not None:
                return
            user_id = str(uuid.uuid4())
            token = secrets.token_urlsafe(32)
            expires = now + self.policy.verification_seconds
            connection.execute("INSERT INTO local_users VALUES (?, ?, ?, 0, 1, ?)", (user_id, email, encoded, now))
            connection.execute("INSERT INTO local_verification_tokens VALUES (?, ?, ?, NULL)", (digest(token), user_id, expires))
            connection.execute("INSERT INTO local_dev_outbox VALUES (?, ?, ?, 'verify_email', ?, ?, ?)", (str(uuid.uuid4()), user_id, digest(token), token, now, expires))
            self._event(connection, user_id, "registered", now)

    def verify_email(self, token, peer):
        self._rate_limit("verify", peer)
        if not valid_token(token):
            raise AuthFailure("invalid_verification", 400)
        now = int(self.clock())
        with self.transaction() as connection:
            row = connection.execute("SELECT user_id, expires_at, consumed_at FROM local_verification_tokens WHERE token_hash=?", (digest(token),)).fetchone()
            if row is None or row["consumed_at"] is not None or row["expires_at"] <= now:
                raise AuthFailure("invalid_verification", 400)
            connection.execute("UPDATE local_verification_tokens SET consumed_at=? WHERE token_hash=?", (now, digest(token)))
            connection.execute("UPDATE local_users SET verified=1 WHERE user_id=?", (row["user_id"],))
            connection.execute("DELETE FROM local_dev_outbox WHERE token_hash=?", (digest(token),))
            self._event(connection, row["user_id"], "verified", now)

    def login(self, email, password, peer, previous_session=None):
        email = normalize_test_email(email)
        self._rate_limit("login", peer, email)
        with closing(connect(self.path, readonly=True)) as connection:
            row = connection.execute("SELECT * FROM local_users WHERE email=?", (email,)).fetchone()
        encoded = dummy_hash() if row is None else row["password_hash"]
        try:
            verified = password_hasher().verify(password, encoded)
        except UnknownHashError:
            raise AuthFailure("authentication_unavailable", 503) from None
        if row is None or not verified or row["verified"] != 1:
            raise AuthFailure("invalid_credentials")
        session, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(self.clock())
        with self.transaction() as connection:
            if valid_token(previous_session):
                connection.execute("UPDATE local_sessions SET revoked_at=? WHERE session_hash=? AND revoked_at IS NULL", (now, digest(previous_session)))
            connection.execute("INSERT INTO local_sessions VALUES (?, ?, ?, ?, ?, NULL)", (digest(session), row["user_id"], digest(csrf), now, now + self.policy.session_seconds))
            self._event(connection, row["user_id"], "login", now)
        return session, csrf

    def authenticate(self, session) -> SessionIdentity:
        if not valid_token(session):
            raise AuthFailure("authentication_required")
        check_schema(self.path)
        with closing(connect(self.path, readonly=True)) as connection:
            row = connection.execute(
                "SELECT u.user_id, u.email, u.created_at, s.csrf_hash FROM local_sessions s JOIN local_users u ON u.user_id=s.user_id WHERE s.session_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.verified=1 AND u.synthetic=1",
                (digest(session), int(self.clock())),
            ).fetchone()
        if row is None:
            raise AuthFailure("authentication_required")
        return SessionIdentity(row["user_id"], row["email"], row["created_at"], row["csrf_hash"])

    def require_csrf(self, session, csrf):
        identity = self.authenticate(session)
        if not valid_token(csrf) or not hmac.compare_digest(digest(csrf), identity.csrf_hash):
            raise AuthFailure("csrf_failed", 403)
        return identity

    def limit_write(self, identity, peer):
        self._rate_limit("workspace_write", peer, identity.user_id)

    def limit_export(self, identity, peer):
        self._rate_limit("report_export", peer, identity.user_id)

    def logout(self, session, csrf):
        identity = self.require_csrf(session, csrf)
        now = int(self.clock())
        with self.transaction() as connection:
            connection.execute("UPDATE local_sessions SET revoked_at=? WHERE session_hash=?", (now, digest(session)))
            self._event(connection, identity.user_id, "logout", now)


def read_local_outbox(path: Path, email: str, now=None):
    email = normalize_test_email(email)
    check_schema(path)
    timestamp = int(time.time() if now is None else now)
    with closing(connect(path, readonly=True)) as connection:
        rows = connection.execute(
            "SELECT o.purpose, o.token, o.expires_at FROM local_dev_outbox o JOIN local_users u ON u.user_id=o.user_id WHERE u.email=? AND o.expires_at>? ORDER BY o.created_at",
            (email, timestamp),
        ).fetchall()
    return [dict(row) for row in rows]
