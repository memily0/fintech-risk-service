"""Verify local accounts and saved reports over HTTP across a process restart."""

import csv
from http.cookiejar import CookieJar
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import urllib.error
import urllib.request

from arcshift_v1.auth import CSRF_COOKIE, SESSION_COOKIE, read_local_outbox
from smoke_v1_backend import check_once


AUTH = "/api/v1/auth"
WORKSPACE = "/api/v1/workspace"
FX = "ru.fx.cbr.usd_rub.official"
NOTE = "Синтетический разбор для проверки сохранённого отчёта."


def smoke():
    with TemporaryDirectory(prefix="arcshift-auth-smoke-") as directory:
        database = Path(directory) / "local.sqlite3"
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        other = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(CookieJar()))
        anonymous = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        identity = {}
        captured = {}
        updated_review = {}

        def call(client, base, route, expected, *, data=None, csrf=None, method=None, cookie=None, binary=False):
            headers = {"Origin": base, "Content-Type": "application/json"}
            if csrf is not None:
                headers["X-CSRF-Token"] = csrf
            if cookie is not None:
                headers["Cookie"] = cookie
            request = urllib.request.Request(base + route, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method)
            try:
                response = client.open(request, timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                if response.status != expected:
                    raise RuntimeError(f"{request.get_method()} {route}: expected {expected}, got {response.status}")
                payload = response.read()
            if binary:
                return payload
            return json.loads(payload) if payload else None

        def sign_in(client, base, email):
            credentials = {"email": email, "password": "Synthetic-only-smoke-password"}
            call(client, base, AUTH + "/register", 202, data=credentials)
            messages = read_local_outbox(database, email)
            if len(messages) != 1:
                raise RuntimeError("Expected one local verification message")
            call(client, base, AUTH + "/verify-email", 204, data={"token": messages[0]["token"]})
            call(client, base, AUTH + "/login", 204, data=credentials)

        def first(base):
            sign_in(opener, base, "smoke@example.test")
            identity.update(call(opener, base, AUTH + "/me", 200))
            catalog = call(opener, base, "/api/v1/market/series", 200)
            history = call(opener, base, f"/api/v1/market/series/{FX}/history?include_revisions=true", 200)
            snapshot_id = history["data_snapshot_id"]
            if snapshot_id != catalog["data_snapshot_id"] or not history["observations"]:
                raise RuntimeError("Catalog and nonempty history must identify the same snapshot")

            csrf = next(cookie.value for cookie in jar if cookie.name == CSRF_COOKIE)
            review = call(opener, base, WORKSPACE + "/reviews", 201, data={"scenario_id": "historical_demo", "note": NOTE}, csrf=csrf)
            captured.update(call(opener, base, WORKSPACE + "/reports", 201, data={
                "review_id": review["review_id"], "expected_revision": review["revision"],
                "expected_data_snapshot_id": snapshot_id, "series_ids": [FX],
            }, csrf=csrf))
            if (captured["data_snapshot_id"] != snapshot_id or captured["review"]["review"] != review
                    or captured["observations"] != history["observations"] or captured["synthetic"] is not True):
                raise RuntimeError("Saved report did not capture the selected review and history")
            new_note = NOTE + " Обновление."
            updated_review.update(call(opener, base, WORKSPACE + "/reviews/" + review["review_id"], 200, method="PATCH", data={
                "expected_revision": review["revision"], "status": "in_review", "note": new_note,
            }, csrf=csrf))
            if updated_review["note"] != new_note or updated_review["revision"] != review["revision"] + 1:
                raise RuntimeError("Review update did not create a new revision")
            sign_in(other, base, "other-smoke@example.test")
            if call(other, base, AUTH + "/me", 200) == identity:
                raise RuntimeError("Both accounts resolved to the same identity")

        def second(base):
            if call(opener, base, AUTH + "/me", 200) != identity:
                raise RuntimeError("Identity was lost across process restart")
            review_path = WORKSPACE + "/reviews/" + updated_review["review_id"]
            if call(opener, base, review_path, 200) != updated_review:
                raise RuntimeError("Updated review was lost across process restart")
            report_id = captured["report_id"]
            detail = WORKSPACE + "/reports/" + report_id
            for suffix in ("", "/export.json"):
                if call(opener, base, detail + suffix, 200) != captured:
                    raise RuntimeError("Saved report changed after editing the review or restarting")
            pdf = call(opener, base, detail + "/export.pdf", 200, binary=True)
            if not pdf.startswith(b"%PDF-"):
                raise RuntimeError("Saved report did not produce a PDF after restart")
            csv_data = call(opener, base, detail + "/export.csv", 200, binary=True)
            rows = list(csv.DictReader(StringIO(csv_data.decode("utf-8-sig"))))
            if len(rows) != len(captured["observations"]) or any(
                row["report_id"] != report_id or row["data_snapshot_id"] != captured["data_snapshot_id"] for row in rows
            ):
                raise RuntimeError("CSV export did not preserve the saved report identity")

            call(other, base, AUTH + "/me", 200)
            for suffix in ("", "/export.json", "/export.csv", "/export.pdf"):
                call(other, base, detail + suffix, 404)

            csrf = next(cookie.value for cookie in jar if cookie.name == CSRF_COOKIE)
            session = next(cookie.value for cookie in jar if cookie.name == SESSION_COOKIE)
            session_header = f"{SESSION_COOKIE}={session}"
            if call(anonymous, base, AUTH + "/me", 200, cookie=session_header) != identity:
                raise RuntimeError("Explicit session cookie did not authenticate the report owner")
            call(opener, base, AUTH + "/logout", 204, data={}, csrf=csrf)
            call(opener, base, AUTH + "/me", 401)
            call(anonymous, base, detail + "/export.pdf", 401, cookie=session_header)

        one = check_once(database, first)
        two = check_once(database, second)
        if any(cookie.name == SESSION_COOKIE for cookie in jar):
            raise RuntimeError("Session cookie was not cleared")
        return {
            "status": "ok", "startup_cycles": 2,
            "session_survived_restart": True, "logout_revoked_session": True,
            "saved_report_survived_restart": True, "private_export_formats_verified": ["json", "csv", "pdf"],
            "foreign_report_access_blocked": True, "revoked_session_export_blocked": True,
            "all_child_servers_stopped": one["server_stopped_after_check"] and two["server_stopped_after_check"],
            "real_email_sent": False, "data_mode": "synthetic", "production_ready": False,
        }


if __name__ == "__main__":
    print(json.dumps(smoke(), indent=2))
