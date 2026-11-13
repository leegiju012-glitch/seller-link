from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import LookupResult, Marketplace
from app.services.ftc import FtcLookupError, lookup_business
from app.services.identifiers import (
    extract_business_number,
    is_smartstore_url,
    is_url,
    normalize_business_number,
)
from app.services.naver import search_smartstores
from app.services.serp import search_marketplaces

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

app = FastAPI(title="Seller Link")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


async def business_number_from_url(client: httpx.AsyncClient, url: str) -> str:
    if not is_smartstore_url(url):
        raise HTTPException(status_code=400, detail="스마트스토어 URL만 입력할 수 있습니다.")
    address = url if "://" in url else f"https://{url}"
    try:
        response = await client.get(address, headers={"User-Agent": "Mozilla/5.0 SellerLink/1.0"}, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail=f"스토어 페이지를 불러오지 못했습니다: {exc}") from exc
    number = extract_business_number(response.text)
    if not number:
        raise HTTPException(status_code=422, detail="공개 HTML에서 유효한 사업자등록번호를 찾지 못했습니다. 번호를 직접 입력하세요.")
    return number


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True, "ftc_configured": bool(settings.ftc_service_key), "serpapi_configured": bool(settings.serpapi_key)}


@app.get("/api/lookup", response_model=LookupResult)
async def lookup(q: str = Query(min_length=1, max_length=2048)) -> LookupResult:
    value = q.strip()
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        source_url: str | None = None
        if is_url(value):
            brno = await business_number_from_url(client, value)
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
        if source_url:
            marketplaces = [item for item in marketplaces if item.platform != "네이버 스마트스토어"]
            marketplaces.insert(0, Marketplace(
                platform="네이버 스마트스토어",
                status="found",
                store_name="입력한 스마트스토어",
                store_url=source_url,
                evidence="입력한 스토어 URL에서 사업자등록번호 추출",
            ))
        for domain in business.domains:
            is_smartstore = "smartstore" in domain.lower()
            marketplaces.append(Marketplace(
                platform="네이버 스마트스토어" if is_smartstore else "자사몰",
                status="found",
                store_name=business.company_name,
                store_url=domain if "://" in domain else None,
                evidence="공정위 공시 인터넷도메인",
            ))
        return LookupResult(input_type=input_type, business=business, marketplaces=marketplaces)
