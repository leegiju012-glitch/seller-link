import asyncio
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import Marketplace
from app.services.identifiers import (
    PublicIdentifiers,
    extract_business_number,
    extract_public_identifiers,
)


PLATFORM_DOMAINS = (
    ("네이버 스마트스토어", "smartstore.naver.com"),
    ("쿠팡", "coupang.com"),
    ("지마켓", "gmarket.co.kr"),
    ("11번가", "11st.co.kr"),
    ("옥션", "auction.co.kr"),
)
MAX_PIVOT_QUERIES = 4
MAX_CANDIDATES = 16


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str | None


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        return False
    try:
        return not ipaddress.ip_address(host).is_private
    except ValueError:
        return True


def _format_phone(phone: str) -> str:
    if len(phone) == 11:
        return f"{phone[:3]}-{phone[3:7]}-{phone[7:]}"
    if len(phone) == 10:
        return f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
    return phone


def _queries(identifiers: PublicIdentifiers) -> list[str]:
    values = [_format_phone(phone) for phone in identifiers.phones]
    values.extend(identifiers.emails)
    return list(dict.fromkeys(values))[:MAX_PIVOT_QUERIES]


def _platform_for(url: str) -> str:
    host = urlparse(url).hostname or ""
    for name, domain in PLATFORM_DOMAINS:
        if host.lower().endswith(domain):
            return name
    return "자사몰"


def _canonical_store_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.lower().endswith("smartstore.naver.com"):
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            return f"https://smartstore.naver.com/{parts[0]}"
    if _platform_for(url) == "자사몰":
        return f"{parsed.scheme}://{parsed.netloc}"
    return url


def _canonical_url_from_html(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    link = soup.find("link", rel=lambda value: value and "canonical" in value)
    meta = soup.find("meta", property="og:url")
    candidate = (link or {}).get("href") or (meta or {}).get("content") or fallback
    return candidate if _is_public_http_url(candidate) else fallback


def _smartstore_id(url: str) -> str | None:
    parsed = urlparse(url)
    if not (parsed.hostname or "").lower().endswith("smartstore.naver.com"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", parts[0]):
        return None
    return parts[0]


async def _search_candidates(
    client: httpx.AsyncClient, query: str, api_key: str
) -> list[Candidate]:
    try:
        response = await client.get(
            "https://serpapi.com/search.json",
            params={
                "engine": "google",
                "q": f'"{query}"',
                "api_key": api_key,
                "hl": "ko",
                "gl": "kr",
                "num": 10,
            },
        )
        response.raise_for_status()
        results = response.json().get("organic_results", [])
    except (httpx.HTTPError, ValueError):
        return []
    candidates = []
    for result in results:
        url = str(result.get("link", ""))
        host = urlparse(url).hostname or ""
        if _is_public_http_url(url) and not host.endswith("google.com"):
            candidates.append(Candidate(url=url, title=str(result.get("title") or "") or None))
    return candidates


async def _fetch_public_html(client: httpx.AsyncClient, url: str) -> str | None:
    current = url
    for _ in range(3):
        if not _is_public_http_url(current):
            return None
        try:
            response = await client.get(
                current,
                headers={"User-Agent": "Mozilla/5.0 SellerLink/1.0"},
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return None
        if 300 <= response.status_code < 400 and response.headers.get("location"):
            current = urljoin(current, response.headers["location"])
            continue
        if response.is_success and "html" in response.headers.get("content-type", "").lower():
            return response.text
        return None
    return None


async def _verify_candidate(
    client: httpx.AsyncClient, candidate: Candidate, brno: str, semaphore: asyncio.Semaphore
) -> Marketplace | None:
    async with semaphore:
        html = await _fetch_public_html(client, candidate.url)
    if not html or extract_business_number(html) != brno:
        return None
    return Marketplace(
        platform=_platform_for(candidate.url),
        status="found",
        store_name=re.sub(r"<[^>]+>", "", candidate.title or "") or None,
        store_url=_canonical_store_url(candidate.url),
        evidence="공개 페이지 사업자등록번호 일치 · 연락처 피봇",
    )


async def discover_cafe24_store(
    client: httpx.AsyncClient, brno: str, smartstore_url: str
) -> Marketplace | None:
    """Check the public Cafe24 default domain when a seller reuses its store ID."""
    store_id = _smartstore_id(smartstore_url)
    if not store_id:
        return None
    candidate_url = f"https://{store_id}.cafe24.com"
    html = await _fetch_public_html(client, candidate_url)
    if not html or extract_business_number(html) != brno:
        return None
    return Marketplace(
        platform="자사몰",
        status="found",
        store_url=_canonical_url_from_html(html, candidate_url),
        evidence="스마트스토어 ID 기반 공개 Cafe24 도메인 · 사업자등록번호 일치",
    )


async def public_identifiers_from_cafe24(
    client: httpx.AsyncClient, smartstore_url: str
) -> PublicIdentifiers | None:
    """Fallback for a rate-limited SmartStore page; never bypasses the restriction."""
    store_id = _smartstore_id(smartstore_url)
    if not store_id:
        return None
    html = await _fetch_public_html(client, f"https://{store_id}.cafe24.com")
    if not html:
        return None
    identifiers = extract_public_identifiers(html)
    return identifiers if identifiers.business_number else None


async def discover_verified_stores(
    client: httpx.AsyncClient,
    brno: str,
    identifiers: PublicIdentifiers,
    settings: Settings,
) -> list[Marketplace]:
    """Find public pages by source-store contacts and keep only exact BRN matches."""
    if not settings.serpapi_key:
        return []
    queries = _queries(identifiers)
    if not queries:
        return []

    searched = await asyncio.gather(*[
        _search_candidates(client, query, settings.serpapi_key) for query in queries
    ])
    candidates: dict[str, Candidate] = {}
    for group in searched:
        for candidate in group:
            candidates.setdefault(candidate.url, candidate)
            if len(candidates) >= MAX_CANDIDATES:
                break
        if len(candidates) >= MAX_CANDIDATES:
            break

    semaphore = asyncio.Semaphore(4)
    verified = await asyncio.gather(*[
        _verify_candidate(client, candidate, brno, semaphore)
        for candidate in candidates.values()
    ])
    stores: dict[tuple[str, str | None], Marketplace] = {}
    for store in verified:
        if store:
            stores.setdefault((store.platform, store.store_url), store)
    return list(stores.values())
