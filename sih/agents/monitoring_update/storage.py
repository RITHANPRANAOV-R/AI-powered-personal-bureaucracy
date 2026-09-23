"""Local monitoring JSON persistence with atomic writes and event log appending."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from .schema import MonitoringResult, StatusEvent


def default_monitoring_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "monitoring"


class MonitoringStore:
    """Local persistence store for monitoring snapshots and status events."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = directory or default_monitoring_dir()
        self.snapshot_path = self.directory / "latest_monitoring.json"
        self.events_path = self.directory / "status_events.jsonl"

    def load_latest(self) -> Optional[MonitoringResult]:
        if not self.snapshot_path.exists():
            return None
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            return MonitoringResult.model_validate(payload)
        except Exception:
            return None

    def save(self, result: MonitoringResult) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.snapshot_path, result.model_dump(mode="json"))

    def append_events(self, events: List[StatusEvent]) -> None:
        if not events:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as f:
            for evt in events:
                f.write(evt.model_dump_json() + "\n")

    def erase(self) -> bool:
        erased = False
        if self.snapshot_path.exists():
            try:
                self.snapshot_path.unlink()
                erased = True
            except OSError:
                pass
        if self.events_path.exists():
            try:
                self.events_path.unlink()
                erased = True
            except OSError:
                pass
        return erased


def _atomic_write_json(target_path: Path, data: dict) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target_path.parent),
        prefix=".tmp_mon_",
        suffix=".json",
    )
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_name, target_path)
    except Exception:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        raise
