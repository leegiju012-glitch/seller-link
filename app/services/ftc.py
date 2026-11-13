from typing import Any

import httpx

from app.config import Settings
from app.models import Business


class FtcLookupError(RuntimeError):
    pass


def _as_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", payload)
    body = response.get("body", response) if isinstance(response, dict) else {}
    items = body.get("items", {}) if isinstance(body, dict) else {}
    if isinstance(items, dict):
        return _as_list(items.get("item") or items.get("items"))
    return _as_list(items)


def _domains(value: Any) -> list[str]:
    if not value:
        return []
    parts = str(value).replace("\n", ",").replace(";", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


async def lookup_business(client: httpx.AsyncClient, brno: str, settings: Settings) -> Business:
    if not settings.ftc_service_key:
        raise FtcLookupError("FTC_SERVICE_KEY가 설정되지 않았습니다.")

    params = {
        "serviceKey": settings.ftc_service_key,
        "pageNo": 1,
        "numOfRows": 20,
        "resultType": "json",
        "brno": brno,
    }
    try:
        response = await client.get(settings.ftc_detail_endpoint, params=params)
        if response.is_error:
            raise FtcLookupError(f"공정위 API가 HTTP {response.status_code}를 반환했습니다.")
        payload = response.json()
    except FtcLookupError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise FtcLookupError(f"공정위 API 호출에 실패했습니다: {exc}") from exc

    header = payload.get("response", {}).get("header", {}) if isinstance(payload, dict) else {}
    if header.get("resultCode") not in (None, "00", "0"):
        raise FtcLookupError(header.get("resultMsg", "공정위 API가 오류를 반환했습니다."))

    rows = _items(payload)
    if not rows:
        raise FtcLookupError("공정위 공시에서 해당 사업자등록번호를 찾지 못했습니다.")

    row = next((item for item in rows if str(item.get("brno", "")).replace("-", "") == brno), rows[0])
    return Business(
        business_number=brno,
        company_name=row.get("bzmnNm") or row.get("bplcNm"),
        representative_name=row.get("rprsvNm"),
        operating_status=row.get("operSttusCdNm") or row.get("bzmnRgsSttusSeNm"),
        mail_order_number=row.get("prmmiMnno"),
        domains=_domains(row.get("domnCn")),
    )
