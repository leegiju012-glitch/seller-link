from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import LookupResult, Marketplace
from app.services.ftc import FtcLookupError, lookup_business
from app.services.identifiers import (
    PublicIdentifiers,
    extract_public_identifiers,
    is_smartstore_url,
    is_url,
    normalize_business_number,
)
from app.services.naver import search_smartstores
from app.services.pivot import (
    discover_cafe24_store,
    discover_verified_stores,
    public_identifiers_from_cafe24,
)
from app.services.serp import search_marketplaces

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

app = FastAPI(title="Seller Link")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


async def public_identifiers_from_url(
    client: httpx.AsyncClient, url: str
) -> PublicIdentifiers:
    if not is_smartstore_url(url):
        raise HTTPException(status_code=400, detail="스마트스토어 URL만 입력할 수 있습니다.")
    address = url if "://" in url else f"https://{url}"
    try:
        response = await client.get(address, headers={"User-Agent": "Mozilla/5.0 SellerLink/1.0"}, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"스토어 페이지를 불러오지 못했습니다: {exc}") from exc
    identifiers = extract_public_identifiers(response.text)
    if not identifiers.business_number:
        raise HTTPException(status_code=422, detail="공개 HTML에서 유효한 사업자등록번호를 찾지 못했습니다. 번호를 직접 입력하세요.")
    return identifiers


def merge_marketplaces(items: list[Marketplace]) -> list[Marketplace]:
    """A verified pivot replaces an unverified result for the same platform."""
    verified_platforms = {item.platform for item in items if item.status == "found"}
    filtered = [
        item for item in items
        if item.status == "found" or item.platform not in verified_platforms
    ]
    unique: dict[tuple[str, str | None, str], Marketplace] = {}
    for item in filtered:
        unique.setdefault((item.platform, item.store_url, item.status), item)
    return list(unique.values())


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, bool | str]:
    return {
        "ok": True,
        "release": "naver-api-hub-2026-11-13",
        "ftc_configured": bool(settings.ftc_service_key),
        "serpapi_configured": bool(settings.serpapi_key),
        "naver_api_hub_configured": bool(
            settings.naver_client_id and settings.naver_client_secret
        ),
    }


@app.get("/api/lookup", response_model=LookupResult)
async def lookup(q: str = Query(min_length=1, max_length=2048)) -> LookupResult:
    value = q.strip()
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        source_url: str | None = None
        source_identifiers: PublicIdentifiers | None = None
        source_used_cafe24_fallback = False
        if is_url(value):
            try:
                source_identifiers = await public_identifiers_from_url(client, value)
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                source_identifiers = await public_identifiers_from_cafe24(client, value)
                source_used_cafe24_fallback = source_identifiers is not None
                if not source_identifiers:
                    raise exc
            brno = source_identifiers.business_number
            assert brno
            input_type = "smartstore_url"
            source_url = value if "://" in value else f"https://{value}"
        else:
            try:
                brno = normalize_business_number(value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            input_type = "business_number"

        try:
            business = await lookup_business(client, brno, settings)
        except FtcLookupError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        marketplaces = await search_marketplaces(client, brno, settings)
        marketplaces = await search_smartstores(client, brno, settings) + marketplaces
        if source_identifiers:
            cafe24_store = await discover_cafe24_store(client, brno, source_url or value)
            if cafe24_store:
                marketplaces.append(cafe24_store)
            marketplaces.extend(await discover_verified_stores(
                client, brno, source_identifiers, settings
            ))
        if source_url:
            marketplaces = [item for item in marketplaces if item.platform != "네이버 스마트스토어"]
            marketplaces.insert(0, Marketplace(
                platform="네이버 스마트스토어",
                status="found",
                store_name="입력한 스마트스토어",
                store_url=source_url,
                evidence=(
                    "입력한 스토어 URL에서 사업자등록번호 추출"
                    if not source_used_cafe24_fallback
                    else "스마트스토어 ID 기반 공개 Cafe24 도메인에서 사업자등록번호 확인"
                ),
            ))
        for domain in business.domains:
            if "://" not in domain:
                continue
            is_smartstore = "smartstore" in domain.lower()
            marketplaces.append(Marketplace(
                platform="네이버 스마트스토어" if is_smartstore else "자사몰",
                status="found",
                store_name=business.company_name,
                store_url=domain,
                evidence="공정위 공시 인터넷도메인",
            ))
        return LookupResult(
            input_type=input_type,
            business=business,
            marketplaces=merge_marketplaces(marketplaces),
        )
