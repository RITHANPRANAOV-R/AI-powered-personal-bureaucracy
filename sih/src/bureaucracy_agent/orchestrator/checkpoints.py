"""SQLite-backed Checkpoint Store for Local Orchestrator state persistence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.bureaucracy_agent.orchestrator.state import OrchestratorState


class SqliteCheckpointStore:
    """Persistent SQLite checkpoint store for workflow execution state."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = base_dir / "data" / "orchestrator_checkpoints.db"
        else:
            self.db_path = Path(db_path)

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize SQLite checkpoint table."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    workflow_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    current_node TEXT NOT NULL,
                    workflow_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_checkpoint(self, state: OrchestratorState) -> None:
        """Save or update an OrchestratorState checkpoint."""
        state.update_timestamp()
        state_dict = state.model_dump(mode="json")
        state_json = json.dumps(state_dict)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (workflow_id, request_id, current_node, workflow_status, updated_at, state_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    request_id = excluded.request_id,
                    current_node = excluded.current_node,
                    workflow_status = excluded.workflow_status,
                    updated_at = excluded.updated_at,
                    state_json = excluded.state_json
                """,
                (
                    state.workflow_id,
                    state.request_id,
                    state.current_node,
                    state.workflow_status,
                    state.updated_at,
                    state_json,
                ),
            )
            conn.commit()

    def load_checkpoint(self, workflow_id: str) -> Optional[OrchestratorState]:
        """Load an OrchestratorState checkpoint by workflow_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT state_json FROM checkpoints WHERE workflow_id = ?",
                (workflow_id,),
            )
            row = cursor.fetchone()
            if row:
                state_dict = json.loads(row["state_json"])
                return OrchestratorState.model_validate(state_dict)
        return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List summary of all persisted workflow checkpoints."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT workflow_id, request_id, current_node, workflow_status, updated_at FROM checkpoints ORDER BY updated_at DESC"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def erase_checkpoints(self) -> int:
        """Erase all saved checkpoints."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM checkpoints")
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count
