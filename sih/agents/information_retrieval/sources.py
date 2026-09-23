"""Allowlisted official fetch/parse. No login, no evasion, no user-supplied URLs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from .config import DEFAULT_ALLOWED_HOSTS, RetrievalConfig, load_retrieval_config
from .schema import OfficialSourceSpec, SourceCheck, SourceCheckStatus, SourceType

MAX_REDIRECTS = 5
MAX_DISCOVERY_LINKS = 3
DISCOVERY_KEYWORDS = (
    "register",
    "registration",
    "document",
    "fresh",
    "step",
    "instruction",
    "faq",
    "apply",
    "passport",
)


DEFAULT_PASSPORT_REGISTRY: tuple[OfficialSourceSpec, ...] = (
    OfficialSourceSpec(
        source_id="ps_home",
        url="https://passportindia.gov.in/AppOnlineProject/welcomeLink",
        title="Passport Seva portal",
        category="portal",
    ),
    OfficialSourceSpec(
        source_id="ps_register",
        url="https://passportindia.gov.in/AppOnlineProject/user/RegistrationBaseAction",
        title="Passport Seva new user registration",
        category="registration",
    ),
    OfficialSourceSpec(
        source_id="ps_steps_pdf",
        url="https://www.passportindia.gov.in/AppOnlineProject/pdf/steps_to_apply_for_passport_services.pdf",
        title="Steps to apply for passport services",
        category="procedure",
    ),
    OfficialSourceSpec(
        source_id="ps_fresh_docs",
        url="https://passportindia.gov.in/AppOnlineProject/docAdvisor/attachmentAdvFreshInp",
        title="Documents required for fresh passport",
        category="documents",
    ),
    OfficialSourceSpec(
        source_id="ps_instructions_pdf",
        url="https://www.passportindia.gov.in/AppOnlineProject/pdf/ApplicationformInstructionBooklet-V3.0.pdf",
        title="Instructions for filling passport application form",
        category="documents",
    ),
    OfficialSourceSpec(
        source_id="mea_passport",
        url="https://www.mea.gov.in/passport-for-indian-nationals.htm",
        title="Ministry of External Affairs — Passport for Indian nationals",
        category="ministry",
    ),
)


@dataclass
class FetchedDocument:
    url: str
    final_url: str
    host: str
    title: str
    source_type: SourceType
    text: str
    html: Optional[str]
    retrieved_at: str
    published_or_updated_at: Optional[str]
    content_hash: str
    headings: list[str] = field(default_factory=list)
    check: SourceCheck = None  # type: ignore[assignment]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    for allowed in allowed_hosts:
        allowed = allowed.lower().strip()
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def canonical_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"https://{(parsed.hostname or '').lower()}{path}{query}"


def resolve_hosts(configured: list[str]) -> list[str]:
    hosts = [h.strip().lower() for h in configured if h and h.strip()]
    return hosts or list(DEFAULT_ALLOWED_HOSTS)


def resolve_registry(configured: list[OfficialSourceSpec]) -> list[OfficialSourceSpec]:
    return list(configured) if configured else list(DEFAULT_PASSPORT_REGISTRY)


class OfficialFetcher:
    def __init__(self, config: Optional[RetrievalConfig] = None, allowed_hosts: Optional[list[str]] = None) -> None:
        self.config = config or load_retrieval_config()
        self.allowed_hosts = resolve_hosts(allowed_hosts or [])

    def fetch(self, url: str, title_hint: str = "") -> tuple[Optional[FetchedDocument], SourceCheck]:
        retrieved_at = utc_now()
        if not host_allowed(url, self.allowed_hosts):
            check = SourceCheck(
                url=url,
                title=title_hint or None,
                status=SourceCheckStatus.SKIPPED,
                retrieved_at=retrieved_at,
                warning="URL host is not on the official allowlist.",
            )
            return None, check

        current = canonical_url(url)
        headers = {"User-Agent": self.config.user_agent, "Accept": "text/html,application/pdf,*/*"}
        try:
            with httpx.Client(
                headers=headers,
                follow_redirects=False,
                timeout=self.config.timeout_seconds,
                verify=True,
            ) as client:
                response, current, redirect_warning = self._follow(client, current)
        except httpx.TimeoutException:
            return None, SourceCheck(
                url=url,
                title=title_hint or None,
                status=SourceCheckStatus.TIMEOUT,
                retrieved_at=retrieved_at,
                warning="Timed out fetching official source.",
            )
        except httpx.HTTPError as exc:
            return None, SourceCheck(
                url=url,
                title=title_hint or None,
                status=SourceCheckStatus.PARSE_FAILED,
                retrieved_at=retrieved_at,
                warning=f"HTTP error: {exc}",
            )

        if redirect_warning or response is None:
            return None, SourceCheck(
                url=url,
                title=title_hint or None,
                host=urlparse(current).hostname,
                status=SourceCheckStatus.REDIRECT_REJECTED if redirect_warning else SourceCheckStatus.PARSE_FAILED,
                retrieved_at=retrieved_at,
                warning=redirect_warning or "No HTTP response.",
            )
        if response.status_code in {401, 403, 407}:
            return None, SourceCheck(
                url=current,
                title=title_hint or None,
                host=urlparse(current).hostname,
                status=SourceCheckStatus.BLOCKED,
                retrieved_at=retrieved_at,
                http_status=response.status_code,
                warning="Access restricted; login or CAPTCHA is out of scope.",
            )
        if response.status_code >= 400:
            return None, SourceCheck(
                url=current,
                title=title_hint or None,
                host=urlparse(current).hostname,
                status=SourceCheckStatus.PARSE_FAILED,
                retrieved_at=retrieved_at,
                http_status=response.status_code,
                warning=f"HTTP {response.status_code}",
            )

        content_type = (response.headers.get("content-type") or "").lower()
        body = response.content[: self.config.max_bytes]
        published = _header_date(response)
        warning = None
        html = None

        if "pdf" in content_type or current.lower().endswith(".pdf"):
            text, headings, warning = _pdf_text(body)
            source_type = SourceType.OFFICIAL_PDF
            title = title_hint or current.rsplit("/", 1)[-1]
        elif "html" in content_type or not content_type or "text/" in content_type:
            text, title, headings, html_published, html = _html_text(body, current, title_hint)
            source_type = SourceType.OFFICIAL_WEBPAGE
            published = published or html_published
        else:
            return None, SourceCheck(
                url=current,
                title=title_hint or None,
                host=urlparse(current).hostname,
                status=SourceCheckStatus.UNSUPPORTED,
                retrieved_at=retrieved_at,
                http_status=response.status_code,
                warning=f"Unsupported content type: {content_type}",
            )

        if not text.strip():
            return None, SourceCheck(
                url=current,
                title=title_hint or None,
                host=urlparse(current).hostname,
                status=SourceCheckStatus.PARSE_FAILED,
                retrieved_at=retrieved_at,
                http_status=response.status_code,
                warning=warning or "No extractable text (OCR is not enabled).",
            )

        digest = hashlib.sha256(_normalize_for_hash(text).encode("utf-8")).hexdigest()
        doc = FetchedDocument(
            url=canonical_url(url),
            final_url=canonical_url(current),
            host=(urlparse(current).hostname or "").lower(),
            title=title,
            source_type=source_type,
            text=text,
            html=html,
            retrieved_at=retrieved_at,
            published_or_updated_at=_header_date(response) or published,
            content_hash=digest,
            headings=headings,
            check=SourceCheck(
                url=canonical_url(current),
                title=title,
                host=(urlparse(current).hostname or "").lower(),
                status=SourceCheckStatus.FETCHED,
                retrieved_at=retrieved_at,
                http_status=response.status_code,
                warning=warning,
            ),
        )
        return doc, doc.check

    def discover_links(self, doc: FetchedDocument) -> list[str]:
        if not doc.html:
            return []
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []
        soup = BeautifulSoup(doc.html, "html.parser")
        found: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue
            absolute = urljoin(doc.final_url, href)
            if not host_allowed(absolute, self.allowed_hosts):
                continue
            label = f"{anchor.get_text(' ', strip=True)} {absolute}".lower()
            if not any(token in label for token in DISCOVERY_KEYWORDS):
                continue
            canon = canonical_url(absolute)
            if canon not in found and canon != doc.final_url:
                found.append(canon)
            if len(found) >= MAX_DISCOVERY_LINKS:
                break
        return found

    def _follow(self, client: httpx.Client, url: str) -> tuple[Optional[httpx.Response], str, Optional[str]]:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not host_allowed(current, self.allowed_hosts):
                return None, current, "Redirect left the official allowlist."
            response = client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    return response, current, "Redirect without Location header."
                nxt = urljoin(current, location)
                if not host_allowed(nxt, self.allowed_hosts):
                    return None, nxt, f"Redirect to non-allowlisted host: {urlparse(nxt).hostname}"
                current = canonical_url(nxt)
                continue
            return response, current, None
        return None, current, "Too many redirects."


def chunk_document(doc: FetchedDocument, max_chars: int = 700) -> list[dict]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", doc.text) if p.strip()]
    if not paragraphs:
        paragraphs = [doc.text.strip()]
    chunks: list[dict] = []
    current = ""
    heading = doc.headings[0] if doc.headings else doc.title
    for para in paragraphs:
        if len(para) < 40 and para.endswith(":") is False and len(para.split()) <= 8:
            heading = para
        if len(current) + len(para) + 1 > max_chars and current:
            chunks.append({"heading": heading, "text": current.strip()})
            current = para
        else:
            current = f"{current}\n{para}".strip()
    if current.strip():
        chunks.append({"heading": heading, "text": current.strip()})
    return chunks[:40]


def bounded_excerpt(text: str, limit: int = 480) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rsplit(" ", 1)[0] + "…"


def _html_text(body: bytes, url: str, title_hint: str) -> tuple[str, str, list[str], Optional[str], str]:
    html = body.decode("utf-8", errors="replace")
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _strip_tags(html), title_hint or url, [], None, html
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    title = title_hint or (soup.title.get_text(" ", strip=True) if soup.title else url)
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
    published = None
    time_el = soup.find("time")
    if time_el and time_el.get("datetime"):
        published = str(time_el.get("datetime"))
    meta = soup.find("meta", attrs={"name": re.compile("last-modified|revised|date", re.I)})
    if meta and meta.get("content"):
        published = published or str(meta.get("content"))
    text = soup.get_text("\n", strip=True)
    return text, title, headings[:12], published, html


def _pdf_text(body: bytes) -> tuple[str, list[str], Optional[str]]:
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(body))
        pages = []
        for page in reader.pages[:12]:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
        if not text:
            return "", [], "No extractable PDF text (OCR is not enabled)."
        heading = text.splitlines()[0].strip() if text.splitlines() else ""
        return text, [heading] if heading else [], None
    except Exception as exc:  # noqa: BLE001
        return "", [], f"PDF parse failed: {exc}"


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _header_date(response: httpx.Response) -> Optional[str]:
    value = response.headers.get("last-modified")
    return value


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()
