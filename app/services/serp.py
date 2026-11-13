import asyncio
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import Marketplace

PLATFORMS = (
    ("쿠팡", "coupang.com"),
    ("네이버 스마트스토어", "smartstore.naver.com"),
    ("지마켓", "gmarket.co.kr"),
    ("11번가", "11st.co.kr"),
    ("옥션", "auction.co.kr"),
)


def _store_name(result: dict) -> str | None:
    title = result.get("title")
    if title:
        return str(title).strip()
    return None


async def _search_platform(
    client: httpx.AsyncClient, platform: str, domain: str, brno: str, key: str
) -> Marketplace:
    formatted = f"{brno[:3]}-{brno[3:5]}-{brno[5:]}"
    params = {"engine": "google", "q": f'site:{domain} "{formatted}"', "api_key": key, "hl": "ko", "gl": "kr", "num": 10}
    try:
        response = await client.get("https://serpapi.com/search.json", params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return Marketplace(platform=platform, status="error", evidence=f"검색 실패: {exc}")

    results = payload.get("organic_results", [])
    for result in results:
        link = result.get("link")
        if not link or not urlparse(link).netloc.endswith(domain):
            continue
        return Marketplace(
            platform=platform,
            status="found",
            store_name=_store_name(result),
            store_url=link,
            evidence="사업자등록번호 도메인 검색 결과",
        )
    return Marketplace(platform=platform, status="not_found")


async def search_marketplaces(client: httpx.AsyncClient, brno: str, settings: Settings) -> list[Marketplace]:
    if not settings.serpapi_key:
        return [Marketplace(platform=name, status="not_checked", evidence="SERPAPI_KEY가 설정되지 않았습니다.") for name, _ in PLATFORMS]
    return list(await asyncio.gather(*[
        _search_platform(client, name, domain, brno, settings.serpapi_key)
        for name, domain in PLATFORMS
    ]))
