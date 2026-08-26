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

# Characters that have no place in a category or industry label but do have a
# place in structuring a prompt or a JSON payload. See the _taxonomy_shape
# validator on BusinessRegistration for why this is defence in depth rather
# than the actual control.
_TAXONOMY_FORBIDDEN = set("{}[]<>|`\\\"")
_TAXONOMY_HAS_LETTER = re.compile(r"[^\W\d_]")


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


class QueryIntent(BaseModel):
    """What the system understood the user to be asking for (M6.1).

    Mirrors app.intent.QueryIntent. Present on a search response only when the
    intent layer produced something it is prepared to stand behind — a null
    `intent` means "no opinion", and the UI shows no panel rather than a
    guess.
    """

    underlying_need: str
    # Always values from the trusted taxonomy (app/taxonomy.py), never free
    # text and never sourced from the businesses collection.
    service_categories: list[str]
    expanded_query: str
    exclusions: list[str] = []
    confidence: float
    # Provenance: "embedding-taxonomy" (classified), "fixture" (checked-in
    # stand-in for the not-yet-built LLM provider), later "llm". Exposed
    # because a client showing the user "I understood you..." should be able
    # to say where that understanding came from.
    source: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    filters: SearchFilters | None = None
    intent: QueryIntent | None = None


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

    # M6.1, security. POST /api/businesses is unauthenticated, so every value
    # below arrives from an anonymous caller, and `industry` / `sub_category`
    # are the two that look like taxonomy once stored: app/filters.py surfaces
    # them via businesses.distinct(), and a category label is exactly the kind
    # of string a query-understanding layer wants to treat as trusted,
    # closed-set content.
    #
    # THE ACTUAL CONTROL IS NOT HERE. It is in app/taxonomy.py: the trusted
    # taxonomy is generated from the checked-in seed dataset by
    # scripts/build_taxonomy.py and is never read from the collection, so
    # nothing written through this endpoint can become taxonomy or reach a
    # prompt, whatever it contains. That removes the write primitive instead of
    # trying to sanitise it, which matters because a character blocklist over
    # free text is a losing position -- there is always another encoding.
    #
    # This validator is the cheap second layer: reject the shapes that are
    # never a real category name (newlines and control characters, the
    # bracket/backtick/pipe family used to structure prompts and payloads, and
    # values with no letter at all, e.g. "-----"). It deliberately does NOT
    # restrict values to the seeded 40: registering a genuinely new category
    # must keep working, and design-doc-v2.md requires such a business to
    # become filterable immediately.
    @field_validator("industry", "sub_category")
    @classmethod
    def _taxonomy_shape(cls, v: str) -> str:
        if any(ch in _TAXONOMY_FORBIDDEN for ch in v):
            raise ValueError(
                "must not contain any of " + " ".join(sorted(_TAXONOMY_FORBIDDEN))
            )
        if any(ch == "\n" or ch == "\r" or ord(ch) < 32 for ch in v):
            raise ValueError("must be a single line without control characters")
        if not _TAXONOMY_HAS_LETTER.search(v):
            raise ValueError("must contain at least one letter")
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
