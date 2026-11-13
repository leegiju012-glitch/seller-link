import re
from dataclasses import dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

BRNO_PATTERN = re.compile(r"(?<!\d)(\d{3}[-\s]?\d{2}[-\s]?\d{5})(?!\d)")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:0\d{1,2}[-\s]?)?\d{3,4}[-\s]?\d{4}(?!\d)")
EMAIL_PATTERN = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])")


@dataclass(frozen=True)
class PublicIdentifiers:
    business_number: str | None
    phones: tuple[str, ...] = ()
    emails: tuple[str, ...] = ()


def normalize_business_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 10 or not is_valid_business_number(digits):
        raise ValueError("유효한 사업자등록번호 10자리를 입력하세요.")
    return digits


def format_business_number(value: str) -> str:
    return f"{value[:3]}-{value[3:5]}-{value[5:]}"


def is_valid_business_number(value: str) -> bool:
    if not value.isdigit() or len(value) != 10:
        return False
    weights = (1, 3, 7, 1, 3, 7, 1, 3, 5)
    total = sum(int(digit) * weight for digit, weight in zip(value[:9], weights))
    total += (int(value[8]) * 5) // 10
    return (10 - (total % 10)) % 10 == int(value[9])


def is_url(value: str) -> bool:
    if "://" in value:
        return bool(urlparse(value).netloc)
    return "." in value.split("/", 1)[0]


def is_smartstore_url(value: str) -> bool:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.netloc.lower().endswith("smartstore.naver.com")


def extract_business_number(html: str) -> str | None:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    candidates = []
    for source in (html, text):
        for match in BRNO_PATTERN.finditer(source):
            raw = match.group(1)
            digits = re.sub(r"\D", "", raw)
            if is_valid_business_number(digits):
                nearby = source[max(0, match.start() - 160): match.end() + 160].lower()
                score = sum(token in nearby for token in ("사업자", "business", "brno", "사업자등록"))
                candidates.append((score, digits))
    return max(candidates, default=(0, None))[1]


def extract_public_identifiers(html: str) -> PublicIdentifiers:
    """Extract only publicly rendered business contact values for search pivots."""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    phones = {
        re.sub(r"\D", "", match.group(0))
        for match in PHONE_PATTERN.finditer(text)
    }
    # Mobile and landline business contacts are useful pivots; short numeric noise is not.
    phones = {phone for phone in phones if 9 <= len(phone) <= 11 and phone.startswith("0")}
    emails = {match.group(0).lower() for match in EMAIL_PATTERN.finditer(text)}
    return PublicIdentifiers(
        business_number=extract_business_number(html),
        phones=tuple(sorted(phones)),
        emails=tuple(sorted(emails)),
    )
