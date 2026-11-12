"""Offline comparison of frozen warning decisions on one synthetic V1 fold."""

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from arcshift_v1.task_definition import PRIMARY_HORIZON_DAYS


@dataclass(frozen=True)
class WarningDay:
    origin: date
    target: Literal[0, 1]
    baseline_warning: bool
    candidate_warning: bool


@dataclass(frozen=True)
class EpisodeOutcome:
    onset: date
    state: Literal["comparable", "fold_boundary", "no_matched_origins"]
    matched_origins: int
    baseline_lead_days: int | None = None
    candidate_lead_days: int | None = None


@dataclass(frozen=True)
class WarningCounts:
    false_alarm_days: int
    warning_days: int
    warned_episodes: int
    missed_episodes: int


@dataclass(frozen=True)
class WarningScorecard:
    matched_origins: int
    negative_origins: int
    episodes: tuple[EpisodeOutcome, ...]
    baseline: WarningCounts
    candidate: WarningCounts


def warning_scorecard(
    days: Iterable[WarningDay],
    episode_onsets: Iterable[date],
    *,
    fold_start: date,
    fold_end: date,
    synthetic: Literal[True],
) -> WarningScorecard:
    """Count day burden and episode outcomes without fitting or selecting a threshold.

    Supply only matched at-risk origins with mature, known labels, and include
    confirmed onsets through the outcome tail (30 days after the last origin).
    Boundary episodes and episodes without a matched origin are reported apart
    from misses. Each positive day links to the next onset only. For covered
    episodes, lead is measured from the first linked warning.
    """
    if synthetic is not True:
        raise ValueError("Only synthetic evaluation is allowed")
    if type(fold_start) is not date or type(fold_end) is not date or fold_start > fold_end:
        raise ValueError("Require an ordered calendar-date fold")

    onsets = tuple(episode_onsets)
    if any(type(onset) is not date for onset in onsets) or len(onsets) != len(set(onsets)):
        raise ValueError("Episode onsets must be distinct calendar dates")
    onsets = sorted(onsets)
    onset_dates = set(onsets)
    horizon = timedelta(days=PRIMARY_HORIZON_DAYS)

    rows = tuple(days)
    origins = set()
    linked = {onset: [] for onset in onsets}
    for row in rows:
        if type(row.origin) is not date or not fold_start <= row.origin <= fold_end:
            raise ValueError("Origin must be a calendar date inside the fold")
        if row.origin in origins or row.origin in onset_dates:
            raise ValueError("Require one matched prediction per at-risk origin, before onset")
        origins.add(row.origin)
        if type(row.target) is not int or row.target not in (0, 1):
            raise ValueError("Require a known binary target for every matched origin")
        if type(row.baseline_warning) is not bool or type(row.candidate_warning) is not bool:
            raise ValueError("Supply explicit warning decisions for both models")
        first_onset = bisect_right(onsets, row.origin)
        positive = first_onset < len(onsets) and onsets[first_onset] <= row.origin + horizon
        if row.target != positive:
            raise ValueError("Target disagrees with the confirmed 30-day onset window")
        if positive:
            linked[onsets[first_onset]].append(row)

    episodes = []
    for onset in onsets:
        window_start = onset - horizon
        window_end = onset - timedelta(days=1)
        if window_end < fold_start or window_start > fold_end:
            continue
        matched = sorted(linked[onset], key=lambda row: row.origin)
        if window_start < fold_start or window_end > fold_end:
            episodes.append(EpisodeOutcome(onset, "fold_boundary", len(matched)))
        elif not matched:
            episodes.append(EpisodeOutcome(onset, "no_matched_origins", 0))
        else:
            baseline_lead = next(((onset - row.origin).days for row in matched if row.baseline_warning), None)
            candidate_lead = next(((onset - row.origin).days for row in matched if row.candidate_warning), None)
            episodes.append(EpisodeOutcome(onset, "comparable", len(matched), baseline_lead, candidate_lead))

    comparable = [episode for episode in episodes if episode.state == "comparable"]
    baseline_hits = sum(episode.baseline_lead_days is not None for episode in comparable)
    candidate_hits = sum(episode.candidate_lead_days is not None for episode in comparable)
    return WarningScorecard(
        matched_origins=len(rows),
        negative_origins=sum(row.target == 0 for row in rows),
        episodes=tuple(episodes),
        baseline=WarningCounts(
            sum(row.baseline_warning and row.target == 0 for row in rows),
            sum(row.baseline_warning for row in rows), baseline_hits, len(comparable) - baseline_hits,
        ),
        candidate=WarningCounts(
            sum(row.candidate_warning and row.target == 0 for row in rows),
            sum(row.candidate_warning for row in rows), candidate_hits, len(comparable) - candidate_hits,
        ),
    )
