from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import Marketplace


def _is_smartstore_url(url: str) -> bool:
    return urlparse(url).netloc.lower().endswith("smartstore.naver.com")


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

    formatted = f"{brno[:3]}-{brno[3:5]}-{brno[5:]}"
    matches: dict[str, Marketplace] = {}
    for keyword in (formatted, brno):
        try:
            response = await client.get(
                "https://naverapihub.apigw.ntruss.com/search/v1/webkr",
                params={"query": f'site:smartstore.naver.com "{keyword}"', "display": 100},
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
            response.raise_for_status()
            items = response.json().get("items", [])
        except (httpx.HTTPError, ValueError):
            return [Marketplace(
                platform="네이버 스마트스토어",
                status="not_checked",
                evidence="네이버 API HUB 연결을 확인하지 못했습니다.",
            )]

        for item in items:
            link = item.get("link", "")
            if _is_smartstore_url(link):
                matches.setdefault(link, Marketplace(
                    platform="네이버 스마트스토어",
                    status="found",
                    store_name=item.get("title", "").replace("<b>", "").replace("</b>", "") or None,
                    store_url=link,
                    evidence="네이버 웹문서 검색 결과",
                ))
    return list(matches.values()) or [Marketplace(platform="네이버 스마트스토어", status="not_found", evidence="네이버 웹문서 검색 결과 없음")]
