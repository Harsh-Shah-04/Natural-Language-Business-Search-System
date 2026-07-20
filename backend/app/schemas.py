"""Pydantic request/response schemas for the search API (M2)."""

from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

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


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
