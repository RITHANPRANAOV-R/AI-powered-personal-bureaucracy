"""SQLite checkpoint store with atomic saves and schema versioning."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.bureaucracy_agent.orchestrator.state import OrchestratorState, load_state_dict

DEFAULT_DB_PATH = Path("data/orchestrator_checkpoints.db")


class SqliteCheckpointStore:
    """Atomic SQLite checkpoint persistence for OrchestratorState."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    workflow_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    state_version TEXT NOT NULL DEFAULT '1.0',
                    current_node TEXT NOT NULL,
                    workflow_status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )
                """
            )
            # Ensure state_version column exists if table was created by older schema
            cursor = conn.execute("PRAGMA table_info(checkpoints)")
            columns = {row["name"] for row in cursor.fetchall()}
            if "state_version" not in columns:
                conn.execute("ALTER TABLE checkpoints ADD COLUMN state_version TEXT NOT NULL DEFAULT '1.0'")
            conn.commit()

    def save_checkpoint(self, state: OrchestratorState) -> None:
        """Atomically persist OrchestratorState to SQLite."""
        state.update_timestamp()
        state_dict = state.model_dump(mode="json")
        state_json = json.dumps(state_dict, ensure_ascii=False)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (
                    workflow_id, request_id, state_version, current_node,
                    workflow_status, updated_at, state_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    request_id=excluded.request_id,
                    state_version=excluded.state_version,
                    current_node=excluded.current_node,
                    workflow_status=excluded.workflow_status,
                    updated_at=excluded.updated_at,
                    state_json=excluded.state_json
                """,
                (
                    state.workflow_id,
                    state.request_id,
                    state.state_version,
                    state.current_node,
                    getattr(state.workflow_status, "value", str(state.workflow_status)),
                    state.updated_at,
                    state_json,
                ),
            )
            conn.commit()

    def load_checkpoint(self, workflow_id: str) -> Optional[OrchestratorState]:
        """Load and deserialize OrchestratorState by workflow_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT state_json FROM checkpoints WHERE workflow_id = ?",
                (workflow_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["state_json"])
            return load_state_dict(data)

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all saved workflow checkpoints summary."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT workflow_id, request_id, current_node, workflow_status, updated_at
                FROM checkpoints
                ORDER BY updated_at DESC
                """
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def erase_checkpoint(self, workflow_id: str) -> bool:
        """Erase a workflow checkpoint by workflow_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE workflow_id = ?",
                (workflow_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
