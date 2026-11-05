# Local Test Accounts

This profile is for synthetic `.test` accounts on loopback only. Never enter
real user data, real passwords or provider credentials. It is not a public
identity service or a production security acceptance.

## Flow

Open `/` and use the account dialog to register a fake address such as
`analyst@example.test`. Use a unique test-only password of 15-128 characters.
Passwords are hashed with pwdlib/Argon2id, not stored in plaintext. The address
is normalized and case-folded without a DNS lookup or actual email delivery.

Retrieve the verification token locally, using the same ARCSHIFT_DB_PATH as
the running service when customized:

```sh
.venv-v1/bin/python -m arcshift_v1.dev_outbox --email analyst@example.test
```

This command deliberately prints a sensitive TEST token to your terminal.
Do not include its output, the SQLite DB or cookies in Git/review packages.
Paste the token into the confirmation form, then sign in. There is no outbox
HTTP endpoint, automatic confirmation, pre-created account or shared login.

## Candidate Contract

`v1-local-auth.1` is separate from unchanged fixture contract `v1-fixture.1`.

| Method And Path | Meaning |
| --- | --- |
| GET /api/v1/auth/capabilities | Explicit local-only boundaries |
| POST /api/v1/auth/register | Generic 202 for first/duplicate registration |
| POST /api/v1/auth/verify-email | Consume one unexpired token; 204 |
| POST /api/v1/auth/login | Require verified identity; set cookies; 204 |
| GET /api/v1/auth/me | Return only the current synthetic identity |
| POST /api/v1/auth/logout | CSRF check, server-side revocation; 204 |

POSTs require the exact same `Origin` as the local service. Logout and all
workspace writes additionally require `X-CSRF-Token` matching the value of
the readable `arcshift_dev_csrf` cookie; the server checks its session-bound
hash, not just equality between user-controlled fields. Other-user resources
cannot be selected by a request-supplied owner ID.

Sessions are random opaque tokens; only hashes of session and CSRF tokens
are stored. Login rotates/revokes the previous browser session, and logout
revokes the server record. Session cookies are host-only, HttpOnly and
SameSite=Strict. **Secure=false is deliberate for loopback HTTP only** and
must not be used for a deployed site. Proxy headers are not trusted.

Development defaults: verification expires after 900 seconds, absolute session
expiry after 3600 seconds, and 10 attempts per action/IP/identity in a fixed
60-second window. Rate counters survive restart; forwarded-address headers
do not bypass them. These are test defaults, not approved public policies.
Errors do not echo passwords/tokens; unknown, unverified and wrong-password
logins receive the same generic response. SQLite files are chmod 0600;
new application runtime directories use 0700.

The local outbox intentionally contains plaintext test verification tokens
until consumption; records are deleted on successful verification. Expired
records are not automatically purged. This is a debug mechanism, not a
production mail queue or a production secret-at-rest design.

## Still Open

Resend, password reset/recovery, account deletion/retention, compromised-password
checks, idle expiry, real transactional mail, delivery failures, public abuse
and load controls, HTTPS/reverse-proxy configuration, production DB/backup
acceptance, privacy documentation and independent security review remain open.
The memory-only fixture profile has no authentication or private state.
No release gate is closed by this local implementation.

Primary engineering references: [FastAPI password hashing](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/),
[OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[OWASP CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
These guide implementation; citing them is not evidence of a completed security audit.
