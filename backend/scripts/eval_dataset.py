"""
Golden evaluation dataset (M4.1).

30 hand-labeled queries across 6 categories, verified against the actual
live dataset structure (not guessed): the 120-business corpus is exactly 3
businesses per sub_category (40 sub_categories x 3), so "all 3 businesses
in sub-category X" is a clean, defensible ground-truth relevant-set for any
query whose intent targets that sub-category. Business/city groupings used
below were pulled directly from the live Atlas cluster before writing these
labels.

`expected_relevant` is a list of business_name values (stable across
reseeds — enforced unique by M1.2 — unlike Mongo _id, which changes on
every reseed). An empty list means "no business in the corpus should be
considered relevant" (used by two edge cases below): precision@k is still
well-defined for these (0.0, since nothing can be relevant), but recall@k
and reciprocal-rank are mathematically undefined for a zero-relevant query
and are excluded from those specific aggregates (see eval.py).

Categories required by the M4.1 spec: semantic, keyword, synonym,
multi_intent, filtered, edge_case.
"""

GOLDEN_QUERIES = [
    # --- semantic: natural phrasing, no literal keyword overlap ---
    {
        "id": "sem-01",
        "query": "I need help filing my business taxes",
        "category": "semantic",
        "filters": None,
        "expected_relevant": ["Smart GST Solutions", "Global GST Industries", "Next GST Enterprises"],
    },
    {
        "id": "sem-02",
        "query": "looking for a place to stay overnight during my business trip",
        "category": "semantic",
        "filters": None,
        "expected_relevant": ["Smart Hotels Solutions", "Global Hotels Industries", "Next Hotels Enterprises"],
    },
    {
        "id": "sem-03",
        "query": "who can help me build a mobile app for my startup",
        "category": "semantic",
        "filters": None,
        "expected_relevant": ["Vertex Software Solutions", "Blue Software Industries", "Apex Software Enterprises"],
    },
    {
        "id": "sem-04",
        "query": "need someone to keep my medicines and health supplies stocked",
        "category": "semantic",
        "filters": None,
        "expected_relevant": ["Elite Pharmacies Solutions", "Green Pharmacies Industries", "Smart Pharmacies Enterprises"],
    },
    {
        "id": "sem-05",
        "query": "want to grow crops without using chemicals",
        "category": "semantic",
        "filters": None,
        "expected_relevant": ["Prime Organic Solutions", "Nova Organic Industries", "Vertex Organic Enterprises"],
    },
    # --- keyword: literal terms straight from products_services/keywords ---
    {
        "id": "kw-01",
        "query": "SOC penetration testing ISO27001 compliance",
        "category": "keyword",
        "filters": None,
        "expected_relevant": ["Global Cybersecurity Solutions", "Next Cybersecurity Industries", "Prime Cybersecurity Enterprises"],
    },
    {
        "id": "kw-02",
        "query": "GST filing GST registration indirect tax",
        "category": "keyword",
        "filters": None,
        "expected_relevant": ["Smart GST Solutions", "Global GST Industries", "Next GST Enterprises"],
    },
    {
        "id": "kw-03",
        "query": "PLC robotics smart factory IIoT",
        "category": "keyword",
        "filters": None,
        "expected_relevant": ["Next Industrial Solutions", "Prime Industrial Industries", "Nova Industrial Enterprises"],
    },
    {
        "id": "kw-04",
        "query": "AWS Azure cloud migration DevOps",
        "category": "keyword",
        "filters": None,
        "expected_relevant": ["Elite Cloud Solutions", "Green Cloud Industries", "Smart Cloud Enterprises"],
    },
    {
        "id": "kw-05",
        "query": "structural steel fabrication welding",
        "category": "keyword",
        "filters": None,
        "expected_relevant": ["Blue Steel Solutions", "Apex Steel Industries", "Elite Steel Enterprises"],
    },
    # --- synonym: different wording, same meaning, no literal token overlap ---
    {
        "id": "syn-01",
        "query": "computer hacking defense and security auditing firm",
        "category": "synonym",
        "filters": None,
        "expected_relevant": ["Global Cybersecurity Solutions", "Next Cybersecurity Industries", "Prime Cybersecurity Enterprises"],
    },
    {
        "id": "syn-02",
        "query": "workplace skill-building and leadership programs",
        "category": "synonym",
        "filters": None,
        "expected_relevant": ["Blue Corporate Solutions", "Apex Corporate Industries", "Elite Corporate Enterprises"],
    },
    {
        "id": "syn-03",
        "query": "crop irrigation machinery supplier",
        "category": "synonym",
        "filters": None,
        "expected_relevant": ["Green Farm Solutions", "Smart Farm Industries", "Global Farm Enterprises"],
    },
    {
        "id": "syn-04",
        "query": "helping shoppers remember and trust a company's image",
        "category": "synonym",
        "filters": None,
        "expected_relevant": ["Next Branding Solutions", "Prime Branding Industries", "Nova Branding Enterprises"],
    },
    {
        "id": "syn-05",
        "query": "search engine visibility and paid ads specialists",
        "category": "synonym",
        "filters": None,
        "expected_relevant": ["Green Digital Solutions", "Smart Digital Industries", "Global Digital Enterprises"],
    },
    # --- multi_intent: query spans two distinct sub-categories ---
    {
        "id": "multi-01",
        "query": "software company that also offers cloud hosting",
        "category": "multi_intent",
        "filters": None,
        "expected_relevant": [
            "Vertex Software Solutions", "Blue Software Industries", "Apex Software Enterprises",
            "Elite Cloud Solutions", "Green Cloud Industries", "Smart Cloud Enterprises",
        ],
    },
    {
        "id": "multi-02",
        "query": "restaurant that also does catering for weddings",
        "category": "multi_intent",
        "filters": None,
        "expected_relevant": [
            "Global Restaurants Solutions", "Next Restaurants Industries", "Prime Restaurants Enterprises",
            "Apex Catering Solutions", "Elite Catering Industries", "Green Catering Enterprises",
        ],
    },
    {
        "id": "multi-03",
        "query": "accounting firm that handles both GST filing and tax audits",
        "category": "multi_intent",
        "filters": None,
        "expected_relevant": [
            "Smart GST Solutions", "Global GST Industries", "Next GST Enterprises",
            "Apex Chartered Solutions", "Elite Chartered Industries", "Green Chartered Enterprises",
        ],
    },
    {
        "id": "multi-04",
        "query": "logistics company handling both cold storage and last-mile delivery",
        "category": "multi_intent",
        "filters": None,
        "expected_relevant": [
            "Nova Cold Solutions", "Vertex Cold Industries", "Blue Cold Enterprises",
            "Smart Courier Solutions", "Global Courier Industries", "Next Courier Enterprises",
        ],
    },
    {
        "id": "multi-05",
        "query": "construction firm doing both interiors and electrical work",
        "category": "multi_intent",
        "filters": None,
        "expected_relevant": [
            "Elite Interior Solutions", "Green Interior Industries", "Smart Interior Enterprises",
            "Global Electrical Solutions", "Next Electrical Industries", "Prime Electrical Enterprises",
        ],
    },
    # --- filtered: query text + filters dict, expected = intersection ---
    {
        "id": "filt-01",
        "query": "food packaging",
        "category": "filtered",
        "filters": {"city": "Mumbai"},
        "expected_relevant": ["Prime Food Solutions"],
    },
    {
        "id": "filt-02",
        "query": "GST expert",
        "category": "filtered",
        "filters": {"city": "Pune"},
        "expected_relevant": ["Global GST Industries"],
    },
    {
        "id": "filt-03",
        "query": "cybersecurity",
        "category": "filtered",
        "filters": {"industry": "Information Technology"},
        "expected_relevant": ["Global Cybersecurity Solutions", "Next Cybersecurity Industries", "Prime Cybersecurity Enterprises"],
    },
    {
        "id": "filt-04",
        "query": "software development",
        "category": "filtered",
        "filters": {"city": "Bengaluru"},
        "expected_relevant": ["Blue Software Industries"],
    },
    {
        "id": "filt-05",
        "query": "catering services",
        "category": "filtered",
        "filters": {"city": "Mumbai"},
        "expected_relevant": ["Elite Catering Industries"],
    },
    # --- edge_case: short/generic, nonsense, casing, empty-result filter, verbose ---
    {
        "id": "edge-01",
        "query": "restaurant",
        "category": "edge_case",
        "filters": None,
        "expected_relevant": ["Global Restaurants Solutions", "Next Restaurants Industries", "Prime Restaurants Enterprises"],
    },
    {
        "id": "edge-02",
        "query": "xyzzy plugh qwertyuiop nonsense gibberish",
        "category": "edge_case",
        "filters": None,
        "expected_relevant": [],  # no business in the corpus should be relevant
    },
    {
        "id": "edge-03",
        "query": "GST EXPERT",
        "category": "edge_case",
        "filters": None,
        "expected_relevant": ["Smart GST Solutions", "Global GST Industries", "Next GST Enterprises"],
    },
    {
        "id": "edge-04",
        "query": "hospitals",
        "category": "edge_case",
        "filters": {"city": "Jaipur"},
        "expected_relevant": [],  # verified: no Hospitals business is in Jaipur
    },
    {
        "id": "edge-05",
        "query": (
            "We are a mid-sized company looking for a specialized firm that can "
            "conduct a thorough security operations center review, perform "
            "penetration testing across our network infrastructure, and help us "
            "achieve ISO27001 compliance certification within the next two quarters."
        ),
        "category": "edge_case",
        "filters": None,
        "expected_relevant": ["Global Cybersecurity Solutions", "Next Cybersecurity Industries", "Prime Cybersecurity Enterprises"],
    },
]
