from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd

from .errors import InputError
from .ranker import OUTPUT_COLUMNS, WEEK_STARTS, RankingStrategy


class RankingService:
    def __init__(self, data_root: Path, output_root: Path, ranker: RankingStrategy):
        self.data_root, self.output_root, self.ranker = data_root, output_root, ranker

    @property
    def predictions_path(self) -> Path:
        return self.output_root / "predictions.csv"

    def run(self, week_start: date | None = None) -> dict:
        weeks = (week_start,) if week_start else WEEK_STARTS
        rows = [self.ranker.rank(self.data_root, week).rows for week in weeks]
        combined = pd.concat(rows, ignore_index=True)[OUTPUT_COLUMNS]
        self._validate(combined, expected_weeks=weeks)
        self.output_root.mkdir(parents=True, exist_ok=True)
        temporary = self.predictions_path.with_suffix(".csv.tmp")
        combined.to_csv(temporary, index=False)
        os.replace(temporary, self.predictions_path)  # callers never observe a half-written result
        metadata = {"weeks": [str(week) for week in weeks], "rows": len(combined)}
        (self.output_root / "run.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return metadata

    def rankings(self, week_start: date) -> list[dict]:
        frame = self._read_output()
        selected = frame[frame.week_start == week_start.isoformat()].sort_values("rank")
        if selected.empty:
            raise InputError(f"No materialised ranking for {week_start}. Call POST /run first.")
        return selected.to_dict(orient="records")

    def explanation(self, gateway_id: str, week_start: date) -> dict:
        for row in self.rankings(week_start):
            if str(row["gateway_id"]) == gateway_id:
                return row
        raise KeyError(f"Gateway {gateway_id!r} is not in the selected 15 for {week_start}.")

    def _read_output(self) -> pd.DataFrame:
        if not self.predictions_path.exists():
            raise InputError("No predictions.csv exists yet. Call POST /run first.")
        return pd.read_csv(self.predictions_path, dtype={"gateway_id": str})

    @staticmethod
    def _validate(frame: pd.DataFrame, expected_weeks: tuple[date, ...]) -> None:
        if list(frame.columns) != OUTPUT_COLUMNS:
            raise InputError(f"Unexpected output columns: {list(frame.columns)}")
        if frame.reason.isna().any() or (frame.reason.str.len() > 300).any():
            raise InputError("Every reason must be present and at most 300 characters.")
        if not pd.api.types.is_numeric_dtype(frame.score):
            raise InputError("score must be numeric.")
        for week in expected_weeks:
            group = frame[frame.week_start == week.isoformat()]
            if len(group) != 15 or set(group["rank"]) != set(range(1, 16)) or group.gateway_id.nunique() != 15:
                raise InputError(f"{week} must have 15 distinct gateways ranked 1 through 15.")
