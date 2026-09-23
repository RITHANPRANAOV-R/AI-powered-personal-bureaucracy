"""Local profile JSON persistence with consent checks and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .schema import FactSourceType, FactStatus, ProfileFact, utc_now

PROFILE_WRAPPER_VERSION = "1.0"


SECRET_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "otp",
    "captcha",
    "pin",
    "cvv",
    "cvc",
    "card_number",
    "credit_card",
    "debit_card",
    "recovery",
    "api_key",
    "secret",
    "token",
    "session",
    "private_key",
)


class ProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[ProfileFact]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        facts_raw = payload.get("facts") if isinstance(payload, dict) else payload
        if not isinstance(facts_raw, list):
            return []
        facts: list[ProfileFact] = []
        for item in facts_raw:
            try:
                fact = ProfileFact.model_validate(item)
            except Exception:
                continue
            if is_secret_key(fact.key):
                continue
            facts.append(fact)
        return facts

    def save(self, facts: list[ProfileFact]) -> None:
        allowed = [fact for fact in facts if fact.confirmed_by_user and not is_secret_key(fact.key)]
        wrapper = {
            "contract_version": PROFILE_WRAPPER_VERSION,
            "updated_at": utc_now(),
            "facts": [fact.model_dump(mode="json") for fact in allowed],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.path, wrapper)

    def upsert_confirmed(self, incoming: Iterable[ProfileFact]) -> list[str]:
        current = {fact.key: fact for fact in self.load()}
        updated_keys: list[str] = []
        for fact in incoming:
            if is_secret_key(fact.key) or not fact.confirmed_by_user:
                continue
            stored = fact.model_copy(
                update={
                    "status": FactStatus.USER_CONFIRMED,
                    "source_type": FactSourceType.PROFILE if fact.source_type != FactSourceType.USER else fact.source_type,
                    "source_ref": f"profile:{fact.key}",
                    "confirmed_by_user": True,
                    "extracted_at": utc_now(),
                }
            )
            current[fact.key] = stored
            updated_keys.append(fact.key)
        self.save(list(current.values()))
        return updated_keys

    def delete_key(self, key: str) -> bool:
        facts = self.load()
        remaining = [fact for fact in facts if fact.key != key]
        if len(remaining) == len(facts):
            return False
        self.save(remaining)
        return True

    def erase(self) -> bool:
        if not self.path.exists():
            return False
        self.path.unlink()
        return True


def is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def _atomic_write_json(path: Path, payload: dict) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=directory,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    try:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    except Exception:
        handle.close()
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
