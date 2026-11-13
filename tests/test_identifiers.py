from app.services.identifiers import extract_business_number, is_url, normalize_business_number


def test_normalize_valid_business_number():
    assert normalize_business_number("220-81-62517") == "2208162517"


def test_extract_prefers_business_number():
    html = "상품번호 13687837463 사업자등록번호 220-81-62517"
    assert extract_business_number(html) == "2208162517"


def test_business_number_is_not_treated_as_a_url():
    assert not is_url("2208162517")
