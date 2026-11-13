import re
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import Marketplace


def _smartstore_root(url: str) -> str | None:
    """Normalize product/category URLs to one canonical store URL."""
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith("smartstore.naver.com"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    return f"https://smartstore.naver.com/{parts[0]}"


def _has_business_number(text: str, brno: str) -> bool:
    return brno in re.sub(r"\D", "", text)


def _plain_text(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value)


def _api_error_evidence(response: httpx.Response) -> str:
    """Return a safe, actionable API error without exposing credentials."""
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    details = payload.get("error", payload) if isinstance(payload, dict) else {}
    code = details.get("errorCode") or details.get("code") or ""
    message = details.get("message") or details.get("errorMessage") or ""

    if response.status_code in (401, 403):
        return "네이버 API HUB 인증 또는 웹 문서 검색 API 권한을 확인하세요."
    if response.status_code == 429:
        return "네이버 API HUB 호출 한도에 도달했습니다."
    suffix = f" ({code})" if code else ""
    if message:
        return f"네이버 API HUB 요청 오류 {response.status_code}{suffix}: {str(message)[:100]}"
    return f"네이버 API HUB 요청 오류 {response.status_code}{suffix}"


async def search_smartstores(
    client: httpx.AsyncClient, brno: str, settings: Settings
) -> list[Marketplace]:
    """Search NAVER web documents through NAVER API HUB."""
    if not settings.naver_client_id or not settings.naver_client_secret:
        return [Marketplace(platform="네이버 스마트스토어", status="not_checked", evidence="네이버 검색 API 키가 설정되지 않았습니다.")]

    matches: dict[str, Marketplace] = {}
    try:
        response = await client.get(
            "https://naverapihub.apigw.ntruss.com/search/v1/webkr",
            params={"query": brno, "display": 100},
            headers={
                "X-NCP-APIGW-API-KEY-ID": settings.naver_client_id,
                "X-NCP-APIGW-API-KEY": settings.naver_client_secret,
            },
        )
        if response.is_error:
            return [Marketplace(
                platform="네이버 스마트스토어",
                status="not_checked",
                evidence=_api_error_evidence(response),
            )]
        items = response.json().get("items", [])
    except (httpx.HTTPError, ValueError):
        return [Marketplace(
            platform="네이버 스마트스토어",
            status="not_checked",
            evidence="네이버 API HUB 연결을 확인하지 못했습니다.",
        )]

    for item in items:
        link = item.get("link", "")
        store_url = _smartstore_root(link)
        searchable_text = f"{item.get('title', '')} {item.get('description', '')}"
        if store_url and _has_business_number(searchable_text, brno):
            matches.setdefault(store_url, Marketplace(
                platform="네이버 스마트스토어",
                status="found",
                store_name=_plain_text(item.get("title", "")) or None,
                store_url=store_url,
                evidence="네이버 웹문서 검색 결과의 사업자등록번호 일치",
            ))
    return list(matches.values()) or [Marketplace(
        platform="네이버 스마트스토어",
        status="not_checked",
        evidence="사업자등록번호가 네이버 웹문서에 색인되지 않아 확인할 수 없습니다.",
    )]
