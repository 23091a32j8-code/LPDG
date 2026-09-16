from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from .errors import InputError


WEEK_STARTS = tuple(pd.date_range("2026-02-02", periods=8, freq="W-MON").date)
OUTPUT_COLUMNS = ["week_start", "gateway_id", "rank", "score", "reason"]


@dataclass(frozen=True)
class RankingResult:
    week_start: date
    rows: pd.DataFrame


class RankingStrategy(ABC):
    """Stable seam: alternate rankers implement this without changing the HTTP API."""

    @abstractmethod
    def rank(self, data_root: Path, week_start: date) -> RankingResult: ...


class RecencyRiskRanker(RankingStrategy):
    """Transparent baseline using stale telemetry and any available offline signal."""

    gateway_candidates = ("gateway_id", "gateway", "gatewayid", "gw_id", "id_gateway")
    time_candidates = ("timestamp", "datetime", "datedt", "date_time", "event_time")

    def rank(self, data_root: Path, week_start: date) -> RankingResult:
        source = self._load(data_root)
        gateway_col = self._column(source, self.gateway_candidates, "gateway identifier")
        time_col = self._column(source, self.time_candidates, "telemetry timestamp")
        frame = source.rename(columns={gateway_col: "gateway_id", time_col: "observed_at"}).copy()
        frame["gateway_id"] = frame["gateway_id"].astype(str).str.strip()
        frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
        cutoff = pd.Timestamp(datetime.combine(week_start, datetime.min.time()), tz="UTC")
        frame = frame[(frame.gateway_id != "") & frame.observed_at.notna() & (frame.observed_at < cutoff)]
        if frame.empty:
            raise InputError(f"No telemetry exists before {week_start.isoformat()}.")

        latest = frame.groupby("gateway_id", as_index=False).observed_at.max()
        latest["stale_hours"] = ((cutoff - latest.observed_at).dt.total_seconds() / 3600).clip(lower=0)
        offline_col = self._optional_column(frame, ("offline", "offline_duration", "offline_hours"))
        if offline_col:
            offline = pd.to_numeric(frame[offline_col], errors="coerce").fillna(0)
            latest = latest.merge(frame.assign(_offline=offline).groupby("gateway_id", as_index=False)._offline.mean(), on="gateway_id")
        else:
            latest["_offline"] = 0.0
        # Recency dominates; an explicit offline measure raises, but never hides, stale devices.
        latest["score"] = (latest.stale_hours + 24 * latest._offline.clip(lower=0)).round(6)
        ranked = latest.sort_values(["score", "gateway_id"], ascending=[False, True]).head(15).copy()
        if len(ranked) != 15:
            raise InputError(f"Need at least 15 gateways before {week_start.isoformat()}; found {len(latest)}.")
        ranked["rank"] = range(1, 16)
        ranked["week_start"] = week_start.isoformat()
        ranked["reason"] = ranked.apply(
            lambda row: f"Last telemetry was {row.stale_hours:.0f} hours before the weekly cutoff; elevated stale-data risk.", axis=1
        )
        return RankingResult(week_start, ranked[OUTPUT_COLUMNS].reset_index(drop=True))

    def _load(self, data_root: Path) -> pd.DataFrame:
        telemetry = data_root / "telemetry"
        candidates = sorted(telemetry.rglob("*.parquet")) + sorted(telemetry.rglob("*.csv"))
        if not candidates:
            raise InputError(f"No telemetry files found below {telemetry}. Mount the supplied bundle at data/.")
        frames: list[pd.DataFrame] = []
        for path in candidates:
            try:
                frames.append(pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path))
            except Exception as exc:
                raise InputError(f"Cannot read {path}: {exc}") from exc
        return pd.concat(frames, ignore_index=True, sort=False)

    @staticmethod
    def _column(frame: pd.DataFrame, candidates: Iterable[str], description: str) -> str:
        found = RecencyRiskRanker._optional_column(frame, candidates)
        if not found:
            raise InputError(f"Telemetry is missing a {description} column. Expected one of: {', '.join(candidates)}.")
        return found

    @staticmethod
    def _optional_column(frame: pd.DataFrame, candidates: Iterable[str]) -> str | None:
        normalized = {str(column).lower().replace(" ", "_"): str(column) for column in frame.columns}
        for candidate in candidates:
            if candidate in normalized:
                return normalized[candidate]
        return None

