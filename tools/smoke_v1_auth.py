"""Real loopback account flow across restart; never print credentials or tokens."""

from contextlib import closing
from http.cookiejar import CookieJar
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import urllib.error
import urllib.request

from smoke_v1_backend import check_once


def smoke():
    with TemporaryDirectory(prefix="arcshift-auth-smoke-") as directory:
        database = Path(directory) / "local.sqlite3"
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        identity = {}
        steps = []

        def call(base, route, expected, data=None, csrf=None):
            headers = {"Origin": base, "Content-Type": "application/json"}
            if csrf is not None:
                headers["X-CSRF-Token"] = csrf
            request = urllib.request.Request(base + "/api/v1/auth" + route, data=None if data is None else json.dumps(data).encode(), headers=headers)
            try:
                response = opener.open(request, timeout=3)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                if response.status != expected:
                    raise RuntimeError("Unexpected status during " + route)
                payload = response.read()
            steps.append(route)
            return json.loads(payload) if payload else None

        def first(base):
            credentials = {"email": "smoke@example.test", "password": "Synthetic-only-smoke-password"}
            call(base, "/register", 202, credentials)
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
                token = connection.execute("SELECT token FROM local_dev_outbox").fetchone()[0]
            call(base, "/verify-email", 204, {"token": token})
            call(base, "/login", 204, credentials)
            identity.update(call(base, "/me", 200))

        def second(base):
            if call(base, "/me", 200) != identity:
                raise RuntimeError("Identity was lost across process restart")
            csrf = next(cookie.value for cookie in jar if cookie.name == "arcshift_dev_csrf")
            call(base, "/logout", 204, {}, csrf)
            call(base, "/me", 401)

        one = check_once(database, first)
        two = check_once(database, second)
        if any(cookie.name == "arcshift_dev_session" for cookie in jar):
            raise RuntimeError("Session cookie was not cleared")
        return {
            "status": "ok", "startup_cycles": 2, "checked_auth_steps": steps,
            "session_survived_restart": True, "logout_revoked_session": True,
            "all_child_servers_stopped": one["server_stopped_after_check"] and two["server_stopped_after_check"],
            "real_email_sent": False, "data_mode": "synthetic", "production_ready": False,
        }


if __name__ == "__main__":
    print(json.dumps(smoke(), indent=2))
