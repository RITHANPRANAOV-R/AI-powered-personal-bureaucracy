"""Structured logging setup for orchestration routes, execution stages, and audit log."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("bureaucracy_agent")

AUDIT_LOG_PATH = Path("data/audit_log.jsonl")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured logging for stdout and file audit."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    handler.setFormatter(formatter)
    
    root = logging.getLogger("bureaucracy_agent")
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


def log_route(from_node: str, to_node: str, reason: str = "") -> None:
    """Log a deterministic route transition line."""
    msg = f"[ROUTE] {from_node} -> {to_node}"
    if reason:
        msg += f" ({reason})"
    logger.info(msg)
    write_audit_event("route_transition", {"from_node": from_node, "to_node": to_node, "reason": reason})


def log_stage(stage: str, details: str = "") -> None:
    """Log an execution browser stage line."""
    msg = f"[STAGE] {stage}"
    if details:
        msg += f": {details}"
    logger.info(msg)
    write_audit_event("execution_stage", {"stage": stage, "details": details})


def write_audit_event(event_type: str, payload: Dict[str, Any], audit_file: Optional[Path] = None) -> None:
    """Append a structured JSON record to the audit JSONL file."""
    target = audit_file or AUDIT_LOG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Could not write audit log: {exc}")
