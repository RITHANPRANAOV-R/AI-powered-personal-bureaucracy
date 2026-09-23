"""Isolated Official Government Knowledge Base Service.

Manages official government rules, procedures, fees, and document guidelines in data/knowledge_base/.
Strictly isolated from personal user document vault data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


class KnowledgeBaseService:
    """Service for managing official Government Knowledge Base sources."""

    def __init__(self, kb_dir: Path | str | None = None) -> None:
        if kb_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.kb_dir = base_dir / "data" / "knowledge_base"
        else:
            self.kb_dir = Path(kb_dir)

        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.kb_dir / "kb_manifest.json"
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        """Ensure default kb_manifest.json exists with official sources."""
        if not self.manifest_path.exists():
            default_manifest = {
                "kb_version": "1.0",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "sources": {
                    "passport_seva_official": {
                        "title": "Passport Seva Official Portal Guidelines",
                        "canonical_url": "https://passportindia.gov.in",
                        "domain": "passportindia.gov.in",
                        "trust_score": 1.0,
                        "service_name": "Passport Seva",
                        "last_verified": datetime.now(timezone.utc).isoformat(),
                    }
                },
            }
            self.manifest_path.write_text(json.dumps(default_manifest, indent=2), encoding="utf-8")

    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest data."""
        self._ensure_manifest()
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"kb_version": "1.0", "sources": {}}

    def list_sources(self) -> List[Dict[str, Any]]:
        """List all official sources in the Knowledge Base."""
        manifest = self._load_manifest()
        return list(manifest.get("sources", {}).values())

    def get_source_metadata(self, source_key: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific official source."""
        manifest = self._load_manifest()
        return manifest.get("sources", {}).get(source_key)
