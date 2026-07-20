"""Pydantic request/response schemas for the search API (M2 + M3.1 + M3.2)."""

from pydantic import BaseModel, Field, field_validator


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
