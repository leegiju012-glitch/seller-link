from app.services.identifiers import (
    extract_business_number,
    extract_public_identifiers,
    is_url,
    normalize_business_number,
)
from app.services.pivot import _canonical_store_url, _smartstore_id


def test_normalize_valid_business_number():
    assert normalize_business_number("220-81-62517") == "2208162517"


def test_extract_prefers_business_number():
    html = "상품번호 13687837463 사업자등록번호 220-81-62517"
    assert extract_business_number(html) == "2208162517"


def test_business_number_is_not_treated_as_a_url():
    assert not is_url("2208162517")


def test_extracts_public_pivot_identifiers():
    identifiers = extract_public_identifiers(
        "사업자등록번호 220-81-62517 대표전화 010-1234-5678 이메일 seller@example.com"
    )
    assert identifiers.business_number == "2208162517"
    assert identifiers.phones == ("01012345678",)
    assert identifiers.emails == ("seller@example.com",)


def test_smartstore_url_canonicalization():
    url = "https://smartstore.naver.com/example/products/123"
    assert _smartstore_id(url) == "example"
    assert _canonical_store_url(url) == "https://smartstore.naver.com/example"
