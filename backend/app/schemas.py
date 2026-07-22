"""Pydantic request/response schemas for the search API (M2 + M3.1 + M3.2)
and business registration (M5.2)."""

import re

from pydantic import BaseModel, Field, field_validator

# Deliberately lenient formats, applied identically on the frontend so both
# sides agree. Not RFC-perfect (that would need the email-validator dep the
# project intentionally avoids) — just enough to reject obvious typos while
# accepting real-world inputs like "example.com" without a scheme.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WEBSITE_RE = re.compile(r"^(https?://)?([\w-]+\.)+[\w-]+(/\S*)?$", re.IGNORECASE)


class SearchFilters(BaseModel):
    industry: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    nature: str | None = Field(default=None, min_length=1, max_length=100)
    sub_category: str | None = Field(default=None, min_length=1, max_length=100)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    filters: SearchFilters | None = None

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class SearchResult(BaseModel):
    id: str
    business_name: str
    nature: str | None = None
    industry: str | None = None
    sub_category: str | None = None
    city: str | None = None
    state: str | None = None
    contact_person: str | None = None
    email: str | None = None
    website: str | None = None
    phone: str | None = None
    business_description: str | None = None
    products_services: str | None = None
    keywords: str | None = None
    specialties: str | None = None
    score: float
    matched_via: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    filters: SearchFilters | None = None


class BusinessRegistration(BaseModel):
    """Input for POST /api/businesses (M5.2).

    Field names match the stored document shape (seed.py's COLUMNS) so the
    registered business is indistinguishable from a seeded one to search.
    `address` is the one field the form adds that seeded docs lack — stored,
    but not part of the search projection. `contact_person`/`specialties`
    aren't collected here; registration.py stores them as None for shape
    uniformity.
    """

    business_name: str = Field(..., min_length=1, max_length=200)
    industry: str = Field(..., min_length=1, max_length=100)
    nature: str = Field(..., min_length=1, max_length=100)
    sub_category: str = Field(..., min_length=1, max_length=100)
    business_description: str = Field(..., min_length=1, max_length=5000)
    products_services: str = Field(..., min_length=1, max_length=5000)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    keywords: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=300)

    @field_validator(
        "business_name",
        "industry",
        "nature",
        "sub_category",
        "business_description",
        "products_services",
        "city",
        "state",
    )
    @classmethod
    def _required_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    # Reject angle brackets in names so HTML-like strings cannot be stored
    # (demo hygiene / input safety). Other fields are unchanged.
    @field_validator("business_name")
    @classmethod
    def _business_name_no_angle_brackets(cls, v: str) -> str:
        if "<" in v or ">" in v:
            raise ValueError("must not contain < or > characters")
        return v

    # Dataset + product convention: nature is Goods or Services only. Free-text
    # here polluted the filter allow-list (e.g. spa service lists typed into
    # Nature). Keep this validator after blank-stripping so the compared value
    # is already normalized.
    @field_validator("nature")
    @classmethod
    def _nature_goods_or_services(cls, v: str) -> str:
        if v not in ("Goods", "Services"):
            raise ValueError("must be 'Goods' or 'Services'")
        return v

    @field_validator("keywords", "address", "phone", "email", "website")
    @classmethod
    def _optional_blank_to_none(cls, v: str | None) -> str | None:
        # Runs before the format checks below (validators fire in definition
        # order): normalise "" / whitespace to None so an empty optional field
        # is simply absent rather than a validation error.
        if v is None:
            return None
        stripped = v.strip()
        return stripped or None

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str | None) -> str | None:
        if v is not None and not _EMAIL_RE.match(v):
            raise ValueError("must be a valid email address")
        return v

    @field_validator("website")
    @classmethod
    def _valid_website(cls, v: str | None) -> str | None:
        if v is not None and not _WEBSITE_RE.match(v):
            raise ValueError("must be a valid website URL")
        return v


class RegisteredBusiness(BaseModel):
    """Response from POST /api/businesses — enough for the frontend to confirm
    and immediately search the new business."""

    id: str
    business_name: str
