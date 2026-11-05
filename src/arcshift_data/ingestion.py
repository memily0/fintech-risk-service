"""Small file-based ingest boundary used by offline tests and fixtures."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import string
import tempfile


REQUIRED_OBSERVATION_FIELDS = {
    "schema_version",
    "series_id",
    "resource_id",
    "units",
    "value",
    "quality",
    "reference_start",
    "reference_end",
    "received_at",
    "snapshot_id",
    "receipt_sha256",
    "is_synthetic",
}


def _parse_timestamp(timestamp_text):
    try:
        timestamp = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError("Timestamp must use ISO format") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone offset")
    return timestamp


def _validate_candidate_observation(observation):
    missing_fields = REQUIRED_OBSERVATION_FIELDS - set(observation)
    if missing_fields:
        raise ValueError(f"Observation is missing fields: {sorted(missing_fields)}")
    if observation["schema_version"] != "candidate.1":
        raise ValueError("Only candidate.1 observations are supported")
    if observation["is_synthetic"] is not True:
        raise PermissionError("Real observations require separate source admission")
    if observation["quality"] != "observed":
        raise ValueError("This candidate store accepts observed fixtures only")
    receipt_hash = observation["receipt_sha256"]
    if (
        not isinstance(receipt_hash, str)
        or len(receipt_hash) != 64
        or any(character not in string.hexdigits.lower() for character in receipt_hash)
    ):
        raise ValueError("receipt_sha256 must contain 64 lowercase hex characters")
    _parse_timestamp(observation["received_at"])


def _observation_identity(observation):
    return "|".join(
        [
            observation["series_id"],
            observation["reference_start"],
            observation["reference_end"],
        ]
    )


def _atomic_write_json(destination, value):
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            json.dump(value, temporary_file, ensure_ascii=False, indent=2, sort_keys=True)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, destination)
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


class SchedulerLock:
    """A basic lock that allows only one local scheduler process."""

    def __init__(self, lock_path):
        self.lock_path = Path(lock_path)
        self.lock_file_descriptor = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_file_descriptor = os.open(
                self.lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as error:
            raise RuntimeError("Another scheduler already owns this lock") from error
        os.write(self.lock_file_descriptor, str(os.getpid()).encode("ascii"))
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        if self.lock_file_descriptor is not None:
            os.close(self.lock_file_descriptor)
            self.lock_file_descriptor = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass


class JsonObservationStore:
    """Keep immutable revisions and an atomically published latest view."""

    def __init__(self, state_path):
        self.state_path = Path(state_path)

    def _read_state(self):
        if not self.state_path.exists():
            return {"schema_version": "candidate.1", "revisions": [], "latest": {}}
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def publish(self, observations, published_at):
        _parse_timestamp(published_at)
        if not observations:
            raise ValueError("At least one observation is required")
        state = self._read_state()
        added_count = 0
        duplicate_count = 0

        for observation in observations:
            _validate_candidate_observation(observation)
            observation_identity = _observation_identity(observation)
            receipt_hash = observation["receipt_sha256"]

            matching_revision = None
            for revision in state["revisions"]:
                if (
                    revision["observation_identity"] == observation_identity
                    and revision["observation"]["receipt_sha256"] == receipt_hash
                ):
                    matching_revision = revision
                    break

            if matching_revision is not None:
                old_observation = matching_revision["observation"]
                comparable_fields = ["series_id", "resource_id", "units", "value", "quality", "reference_start", "reference_end", "dimensions"]
                for field_name in comparable_fields:
                    if old_observation.get(field_name) != observation.get(field_name):
                        raise ValueError("One receipt hash cannot describe different normalized data")
                duplicate_count += 1
                continue

            revision_number = 1
            for revision in state["revisions"]:
                if revision["observation_identity"] == observation_identity:
                    revision_number = max(revision_number, revision["revision_number"] + 1)

            revision_record = {
                "observation_identity": observation_identity,
                "revision_number": revision_number,
                "ingested_at": published_at,
                "observation": observation,
            }
            state["revisions"].append(revision_record)
            added_count += 1

            current_latest = state["latest"].get(observation_identity)
            if current_latest is None:
                state["latest"][observation_identity] = revision_record
            else:
                new_received_time = _parse_timestamp(observation["received_at"])
                old_received_time = _parse_timestamp(current_latest["observation"]["received_at"])
                if new_received_time >= old_received_time:
                    state["latest"][observation_identity] = revision_record

        if added_count == 0:
            return {
                "added_count": 0,
                "duplicate_count": duplicate_count,
                "snapshot_id": state["snapshot_id"],
            }

        state["published_at"] = published_at
        state_without_id = dict(state)
        state_without_id.pop("snapshot_id", None)
        canonical_state = json.dumps(state_without_id, sort_keys=True, separators=(",", ":"))
        state["snapshot_id"] = hashlib.sha256(canonical_state.encode("utf-8")).hexdigest()
        _atomic_write_json(self.state_path, state)

        return {
            "added_count": added_count,
            "duplicate_count": duplicate_count,
            "snapshot_id": state["snapshot_id"],
        }

    def read(self):
        return self._read_state()


def receipt_freshness_state(observation, checked_at, maximum_receipt_age_seconds, calendar_state):
    """Classify fixture receipt age; this is not a production calendar verdict."""
    if calendar_state not in {"open", "closed", "holiday"}:
        raise ValueError("calendar_state must be open, closed, or holiday")
    if observation is None or observation.get("quality") != "observed":
        return "unavailable"
    if calendar_state == "closed":
        return "market_closed"
    if calendar_state == "holiday":
        return "calendar_holiday"
    if maximum_receipt_age_seconds < 0:
        raise ValueError("maximum_receipt_age_seconds cannot be negative")

    checked_time = _parse_timestamp(checked_at)
    received_time = _parse_timestamp(observation["received_at"])
    receipt_age_seconds = (checked_time - received_time).total_seconds()
    if receipt_age_seconds < 0:
        return "clock_error"
    if receipt_age_seconds > maximum_receipt_age_seconds:
        return "stale"
    return "fresh"
