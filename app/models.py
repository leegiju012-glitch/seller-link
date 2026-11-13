from pydantic import BaseModel, Field


class Business(BaseModel):
    business_number: str
    company_name: str | None = None
    representative_name: str | None = None
    operating_status: str | None = None
    mail_order_number: str | None = None
    domains: list[str] = Field(default_factory=list)


class Marketplace(BaseModel):
    platform: str
    status: str
    store_name: str | None = None
    store_url: str | None = None
    evidence: str | None = None


class LookupResult(BaseModel):
    input_type: str
    business: Business
    marketplaces: list[Marketplace]
    warnings: list[str] = Field(default_factory=list)


class ExtensionLookupRequest(BaseModel):
    business_number: str
    source_url: str
    phones: list[str] = Field(default_factory=list, max_length=10)
    emails: list[str] = Field(default_factory=list, max_length=10)
