"""Isolated Personal Document Vault Service.

Manages user documents stored in data/vault/ with upload authorization tracking
and directory safety checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


class VaultService:
    """Service for isolated Personal Document Vault management."""

    def __init__(self, vault_dir: Path | str | None = None) -> None:
        if vault_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent
            self.vault_dir = base_dir / "data" / "vault"
        else:
            self.vault_dir = Path(vault_dir)

        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.vault_dir / "vault_manifest.json"
        self._ensure_manifest()

    def _ensure_manifest(self) -> None:
        """Ensure vault_manifest.json exists."""
        if not self.manifest_path.exists():
            default_manifest = {
                "vault_version": "1.0",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "documents": {},
            }
            self.manifest_path.write_text(json.dumps(default_manifest, indent=2), encoding="utf-8")

    def _load_manifest(self) -> Dict[str, Any]:
        """Load manifest data."""
        self._ensure_manifest()
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"vault_version": "1.0", "documents": {}}

    def _save_manifest(self, data: Dict[str, Any]) -> None:
        """Save manifest data."""
        self.manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def is_authorized_for_upload(self, doc_key: str) -> bool:
        """Check if a document key or file in vault is authorized for external upload."""
        manifest = self._load_manifest()
        docs = manifest.get("documents", {})
        doc_info = docs.get(doc_key)
        if not doc_info:
            # Check by filename match
            for info in docs.values():
                if info.get("filename") == doc_key or info.get("doc_id") == doc_key:
                    return bool(info.get("authorized_for_upload", False))
            return False
        return bool(doc_info.get("authorized_for_upload", False))

    def set_upload_authorization(self, doc_key: str, authorized: bool = True) -> bool:
        """Set authorization status for uploading a document."""
        manifest = self._load_manifest()
        docs = manifest.get("documents", {})
        if doc_key in docs:
            docs[doc_key]["authorized_for_upload"] = authorized
            self._save_manifest(manifest)
            return True
        return False

    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents registered in the vault."""
        manifest = self._load_manifest()
        return list(manifest.get("documents", {}).values())

    def get_document_path(self, doc_filename: str) -> Optional[Path]:
        """Get safe absolute path to file in vault, preventing path traversal."""
        target_path = (self.vault_dir / doc_filename).resolve()
        # Path traversal guard
        try:
            target_path.relative_to(self.vault_dir.resolve())
        except ValueError:
            raise PermissionError(f"Access denied: file path '{doc_filename}' leaves vault directory.")
        
        if target_path.exists():
            return target_path
        return None
