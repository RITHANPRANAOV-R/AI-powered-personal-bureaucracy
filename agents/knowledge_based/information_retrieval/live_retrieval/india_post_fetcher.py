"""Official OGD postal lookup, deliberately independent of UIDAI execution.

Set DATA_GOV_IN_API_KEY in the server environment. No credential is returned.
Taluka is postal source data, NOT a resolved UIDAI Village/Town/City.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..config import RetrievalConfig
from ..schemas.source import Source, SourceType
from ..sources.source_registry import SourceRegistry

OGD_RESOURCE_ID = "61761d14-3856-4354-a74c-f3f0054f492f"
OGD_URL = f"https://api.data.gov.in/resource/{OGD_RESOURCE_ID}"
SOURCE_ID = "india-post-all-india-pincode-directory"


class PostalLookupStatus(str, Enum):
    SUCCESS = "success"
    MULTIPLE_RECORDS = "multiple_records"
    INVALID_PIN = "invalid_pin"
    EMPTY_RESULT = "empty_result"
    NOT_CONFIGURED = "not_configured"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    MALFORMED_RESPONSE = "malformed_response"
    SOURCE_UNAVAILABLE = "source_unavailable"


class PostalRecord(BaseModel):
    pincode: str
    state_name: str | None = None
    district: str | None = None
    office_name: str | None = None
    taluka: str | None = None
    circle: str | None = None
    division: str | None = None
    region: str | None = None
    source_record: dict[str, Any] = Field(default_factory=dict)


class PostalLookupResult(BaseModel):
    status: PostalLookupStatus
    queried_pin: str | None = None
    source: Source
    source_resource_id: str = OGD_RESOURCE_ID
    retrieved_at: str | None = None
    records: list[PostalRecord] = Field(default_factory=list)
    http_status_code: int | None = None
    error_message: str | None = None


class _CredentialFilter(logging.Filter):
    """Redact OGD query credentials from httpx's automatic request log."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = re.sub(
            r"(?i)(api(?:-|%2d|_)key(?:=|%3d))[^&\s\"']+",
            r"\1[REDACTED]", message,
        )
        record.args = ()
        return True


class IndiaPostLocationFetcher:
    """Return all postal candidates, never choose an office or infer a VTC.

    Uses the existing source registry/model and HTTP library. The JSON API is
    intentionally not routed through LiveGovernmentFetcher's HTML parser.
    A failed page invalidates the lookup rather than returning partial success.
    """

    def __init__(
        self,
        config: RetrievalConfig | None = None,
        source_registry: SourceRegistry | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.config = config or RetrievalConfig()
        self.registry = source_registry or SourceRegistry(include_defaults=False)
        self.transport = transport
        self.source = Source(
            source_id=SOURCE_ID,
            authority="Department of Posts, Government of India",
            domain="india_post",
            url=OGD_URL,
            document_title="All India Pincode Directory",
            source_type=SourceType.GOVERNMENT_API,
            # Not yet checked; real lookup time is recorded on the result.
            last_checked="",
        )
        self.registry.register_source(self.source)

    def lookup(self, pin: str) -> PostalLookupResult:
        result = PostalLookupResult(
            status=PostalLookupStatus.INVALID_PIN, source=self.source.model_copy(deep=True),
        )
        if not isinstance(pin, str) or re.fullmatch(r"[1-9][0-9]{5}", pin) is None:
            result.error_message = "PIN must be a six-digit string beginning with 1-9."
            return result
        result.queried_pin = pin
        secret = self.config.data_gov_in_api_key
        if secret is None or not secret.get_secret_value().strip():
            result.status = PostalLookupStatus.NOT_CONFIGURED
            result.error_message = "DATA_GOV_IN_API_KEY is not configured."
            return result
        if not self.registry.is_authoritative(OGD_URL, "india_post"):
            result.status = PostalLookupStatus.SOURCE_UNAVAILABLE
            result.error_message = "Official source authority could not be validated."
            return result

        key = secret.get_secret_value()
        http_logger = logging.getLogger("httpx")
        redactor = _CredentialFilter()
        http_logger.addFilter(redactor)
        result.retrieved_at = datetime.now(timezone.utc).isoformat()
        records: list[PostalRecord] = []
        expected_total: int | None = None
        try:
            with httpx.Client(
                transport=self.transport, timeout=15.0, follow_redirects=False,
                trust_env=False,
            ) as client:
                # Bound pathological pagination. Never truncate into success.
                for _ in range(1000):
                    response = client.get(OGD_URL, params={
                        "api-key": key, "format": "json", "filters[pincode]": pin,
                        "offset": len(records), "limit": 100,
                    })
                    result.http_status_code = response.status_code
                    if response.status_code != 200:
                        result.status = PostalLookupStatus.HTTP_ERROR
                        result.error_message = "Official OGD API returned a non-success HTTP status."
                        return result
                    try:
                        payload = response.json()
                        # API error echoes must never leak the supplied credential.
                        if key in json.dumps(payload, ensure_ascii=False):
                            raise ValueError("Credential echoed")
                        page, total = self._parse_page(payload, pin)
                        if expected_total is not None and total != expected_total:
                            raise ValueError("Total changed during lookup")
                        expected_total = total
                        if len(records) + len(page) > total or (not page and len(records) < total):
                            raise ValueError("Incomplete or inconsistent pagination")
                        records.extend(page)
                    except (ValueError, TypeError):
                        result.status = PostalLookupStatus.MALFORMED_RESPONSE
                        result.error_message = "Official OGD API returned malformed or inconsistent postal data."
                        return result
                    if len(records) == total:
                        result.records = records
                        result.source.last_checked = result.retrieved_at
                        result.status = (
                            PostalLookupStatus.EMPTY_RESULT if not records else
                            PostalLookupStatus.SUCCESS if len(records) == 1 else
                            PostalLookupStatus.MULTIPLE_RECORDS
                        )
                        return result
                result.status = PostalLookupStatus.MALFORMED_RESPONSE
                result.error_message = "Official OGD API pagination exceeded the safety limit."
        except httpx.TimeoutException:
            result.status = PostalLookupStatus.TIMEOUT
            result.error_message = "Official OGD API request timed out."
        except httpx.HTTPError:
            result.status = PostalLookupStatus.SOURCE_UNAVAILABLE
            result.error_message = "Official OGD API is unavailable."
        finally:
            http_logger.removeFilter(redactor)
        return result

    @staticmethod
    def _parse_page(payload: Any, pin: str) -> tuple[list[PostalRecord], int]:
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise ValueError("Missing records")
        total = payload.get("total")
        if isinstance(total, str) and re.fullmatch(r"[0-9]+", total):
            total = int(total)
        if type(total) is not int or total < 0:
            raise ValueError("Invalid total")
        if payload.get("status") not in (None, "ok", "success"):
            raise ValueError("API error envelope")
        records = []
        aliases = {
            "state_name": ("statename", "state"),
            "district": ("district", "districtname"),
            "office_name": ("officename", "office"),
            "taluka": ("taluka",),
            "circle": ("circle", "circlename"),
            "division": ("division", "divisionname"),
            "region": ("region", "regionname"),
        }
        for raw in payload["records"]:
            if not isinstance(raw, dict):
                raise ValueError("Invalid record")
            normalized = {re.sub(r"[\s_-]", "", k.lower()): v for k, v in raw.items()}
            raw_pin = normalized.get("pincode")
            if isinstance(raw_pin, bool) or str(raw_pin) != pin:
                raise ValueError("Record PIN differs from query")
            fields = {}
            for name, choices in aliases.items():
                value = next((normalized[k] for k in choices if k in normalized), None)
                if value is not None and not isinstance(value, str):
                    raise ValueError("Invalid postal field")
                fields[name] = value.strip() or None if isinstance(value, str) else None
            records.append(PostalRecord(pincode=pin, source_record=raw, **fields))
        return records, total
