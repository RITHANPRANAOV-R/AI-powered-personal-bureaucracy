"""Authorized vault scan. Paths come from configuration, never from document text."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .schema import FileScanStatus, ScannedFile

SUPPORTED_TEXT = {".txt", ".md"}
SUPPORTED_PDF = {".pdf"}
MAX_FILE_BYTES = 1_000_000
MAX_EXCERPT_CHARS = 4000


class VaultAccessError(ValueError):
    """Raised when a path is not inside the authorized vault."""


@dataclass
class VaultDocument:
    relative_path: str
    text: str
    scan: ScannedFile


def resolve_vault_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise VaultAccessError(f"Vault directory does not exist: {resolved}")
    if not resolved.is_dir():
        raise VaultAccessError(f"Vault path is not a directory: {resolved}")
    return resolved


def assert_inside_vault(vault_dir: Path, candidate: Path) -> Path:
    vault = vault_dir.resolve()
    try:
        resolved = candidate.expanduser().resolve()
        resolved.relative_to(vault)
    except (ValueError, OSError) as exc:
        raise VaultAccessError(f"Refusing to open path outside the authorized vault: {candidate}") from exc
    return resolved


def relative_to_vault(vault_dir: Path, path: Path) -> str:
    rel = path.resolve().relative_to(vault_dir.resolve())
    return rel.as_posix()


def iter_vault_files(vault_dir: Path) -> Iterable[Path]:
    vault = vault_dir.resolve()
    for item in sorted(vault.rglob("*")):
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue
        try:
            assert_inside_vault(vault, item)
        except VaultAccessError:
            continue
        yield item


def scan_vault(vault_dir: Path) -> tuple[list[VaultDocument], list[ScannedFile], list[str]]:
    documents: list[VaultDocument] = []
    scanned: list[ScannedFile] = []
    warnings: list[str] = []

    for path in iter_vault_files(vault_dir):
        rel = relative_to_vault(vault_dir, path)
        suffix = path.suffix.lower()
        try:
            size = path.stat().st_size
        except OSError as exc:
            scan = ScannedFile(
                relative_path=rel,
                status=FileScanStatus.UNREADABLE,
                media_type=suffix or "unknown",
                warning=str(exc),
            )
            scanned.append(scan)
            warnings.append(f"Could not stat {rel}.")
            continue

        if size > MAX_FILE_BYTES:
            scan = ScannedFile(
                relative_path=rel,
                status=FileScanStatus.SKIPPED,
                media_type=suffix or "unknown",
                warning=f"File exceeds {MAX_FILE_BYTES} bytes",
            )
            scanned.append(scan)
            warnings.append(f"Skipped {rel}: file too large.")
            continue

        if suffix in SUPPORTED_TEXT:
            text, warning = _read_text(path)
            if text is None:
                scan = ScannedFile(
                    relative_path=rel,
                    status=FileScanStatus.UNREADABLE,
                    media_type="text",
                    warning=warning,
                )
                scanned.append(scan)
                warnings.append(f"Unreadable text file {rel}.")
                continue
            scan = ScannedFile(
                relative_path=rel,
                status=FileScanStatus.READ,
                media_type="text",
                character_count=len(text),
            )
            scanned.append(scan)
            documents.append(VaultDocument(relative_path=rel, text=text, scan=scan))
            continue

        if suffix in SUPPORTED_PDF:
            text, warning = _read_pdf(path)
            if text is None:
                scan = ScannedFile(
                    relative_path=rel,
                    status=FileScanStatus.UNREADABLE,
                    media_type="pdf",
                    warning=warning or "No extractable text (scanned PDF is unsupported; OCR is not enabled).",
                )
                scanned.append(scan)
                warnings.append(f"PDF {rel} has no extractable text.")
                continue
            scan = ScannedFile(
                relative_path=rel,
                status=FileScanStatus.READ,
                media_type="pdf",
                character_count=len(text),
                warning=warning,
            )
            scanned.append(scan)
            documents.append(VaultDocument(relative_path=rel, text=text, scan=scan))
            continue

        scanned.append(
            ScannedFile(
                relative_path=rel,
                status=FileScanStatus.UNSUPPORTED,
                media_type=suffix or "unknown",
                warning="Unsupported format. Place .txt, .md, or text-based .pdf files only.",
            )
        )
        warnings.append(f"Unsupported file type: {rel}")

    return documents, scanned, warnings


def excerpt_for_model(text: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    compact = text.strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "\n[truncated]"


def _read_text(path: Path) -> tuple[Optional[str], Optional[str]]:
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1"), "Decoded as latin-1"
        except OSError as exc:
            return None, str(exc)
    except OSError as exc:
        return None, str(exc)


def _read_pdf(path: Path) -> tuple[Optional[str], Optional[str]]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None, "pypdf is not installed"

    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if not text:
            return None, "No extractable text (likely a scanned PDF). OCR is not enabled."
        return text, None
    except Exception as exc:  # noqa: BLE001 — parser failures are reported as unreadable
        return None, f"PDF parse failed: {exc}"
