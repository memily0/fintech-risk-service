"""Offline worker boundary that publishes through the shared market store."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from arcshift_data import SchedulerLock, merge_observation_state, run_with_bounded_retry

from .market import MarketStore


@dataclass(frozen=True)
class SourceJob:
    name: str
    fetch_payload: Callable[[], bytes]
    parse_payload: Callable[[bytes], list[dict]]
    maximum_attempts: int = 3
    wait_seconds: tuple[float, ...] = (1, 2)


@dataclass(frozen=True)
class WorkerResult:
    data_snapshot_id: str
    added_count: int
    duplicate_count: int
    source_count: int


class DataWorker:
    """Fetch, normalize, revise and publish without a parallel database."""

    def __init__(self, market_store: MarketStore, sleep_function=None):
        if market_store.path is None:
            raise ValueError("The worker requires the shared persistent market store")
        self.market_store = market_store
        database_path = Path(market_store.path)
        self.lock_path = database_path.with_name(database_path.name + ".worker.lock")
        self.sleep_function = sleep_function

    def run(self, jobs, published_at):
        jobs = tuple(jobs)
        if not jobs:
            raise ValueError("At least one source job is required")
        with SchedulerLock(self.lock_path):
            observations = []
            for job in jobs:
                retry_options = {
                    "maximum_attempts": job.maximum_attempts,
                    "wait_seconds": job.wait_seconds,
                }
                if self.sleep_function is not None:
                    retry_options["sleep_function"] = self.sleep_function
                payload = run_with_bounded_retry(job.fetch_payload, **retry_options)
                if not isinstance(payload, bytes):
                    raise TypeError(f"{job.name} fetch must return bytes")
                parsed = job.parse_payload(payload)
                if not isinstance(parsed, list) or not parsed:
                    raise ValueError(f"{job.name} parser returned no observations")
                observations.extend(parsed)

            current = self.market_store.read().model_dump(mode="json")
            next_state, result = merge_observation_state(current, observations, published_at)
            if result["added_count"]:
                snapshot_id = self.market_store.publish(next_state)
            else:
                snapshot_id = "market-" + result["snapshot_id"]
            return WorkerResult(
                data_snapshot_id=snapshot_id,
                added_count=result["added_count"],
                duplicate_count=result["duplicate_count"],
                source_count=len(jobs),
            )
