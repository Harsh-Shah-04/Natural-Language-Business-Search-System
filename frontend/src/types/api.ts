// Types mirroring the backend API contract (backend/app/schemas.py).
// Kept in one place so the API layer and components share a single source
// of truth for the shapes the FastAPI backend sends and expects.

/** The five filterable fields, matching SearchFilters on the backend. */
export interface SearchFilters {
  industry?: string;
  city?: string;
  state?: string;
  nature?: string;
  sub_category?: string;
}

/** A field name that can be filtered on — the keys of SearchFilters. */
export type FilterField = keyof SearchFilters;

export const FILTER_FIELDS: FilterField[] = [
  'industry',
  'city',
  'state',
  'nature',
  'sub_category',
];

/** Human-readable labels for each filter dropdown. */
export const FILTER_LABELS: Record<FilterField, string> = {
  industry: 'Industry',
  city: 'City',
  state: 'State',
  nature: 'Nature',
  sub_category: 'Sub Category',
};

/** Request body for POST /api/search. */
export interface SearchRequest {
  query: string;
  limit?: number;
  filters?: SearchFilters | null;
}

/** How a result was retrieved — set by the hybrid pipeline / RRF. */
export type MatchedVia = 'semantic' | 'keyword' | 'both' | string;

/** One business result, matching SearchResult on the backend. */
export interface SearchResult {
  id: string;
  business_name: string;
  nature: string | null;
  industry: string | null;
  sub_category: string | null;
  city: string | null;
  state: string | null;
  contact_person: string | null;
  email: string | null;
  website: string | null;
  phone: string | null;
  business_description: string | null;
  products_services: string | null;
  keywords: string | null;
  specialties: string | null;
  score: number;
  matched_via: MatchedVia;
}

/**
 * Where an inferred intent came from. Mirrors app/intent.py's providers.
 * `embedding-taxonomy` = classified against the service taxonomy;
 * `fixture` = checked-in stand-in for the not-yet-built LLM provider.
 */
export type IntentSource = 'embedding-taxonomy' | 'fixture' | 'llm' | string;

/**
 * What the backend understood the query to mean (M6.1), mirroring QueryIntent
 * in backend/app/schemas.py. Null on the response when the intent layer had no
 * opinion it was prepared to stand behind — the UI shows nothing in that case
 * rather than a guess.
 */
export interface QueryIntent {
  underlying_need: string;
  /** Always values from the backend's trusted taxonomy, never free text. */
  service_categories: string[];
  expanded_query: string;
  exclusions: string[];
  confidence: number;
  source: IntentSource;
}

/** Response body from POST /api/search. */
export interface SearchResponse {
  query: string;
  results: SearchResult[];
  filters: SearchFilters | null;
  intent: QueryIntent | null;
}

/**
 * Response from GET /api/filters/values: each filterable field mapped to its
 * allowed values (the backend derives these from the live DB and sorts them).
 */
export type FilterValues = Record<FilterField, string[]>;

// ---- Registration (M5.2) --------------------------------------------------

/** Request body for POST /api/businesses. Mirrors backend BusinessRegistration. */
export interface BusinessRegistration {
  business_name: string;
  industry: string;
  nature: string;
  sub_category: string;
  business_description: string;
  products_services: string;
  city: string;
  state: string;
  keywords?: string;
  address?: string;
  phone?: string;
  email?: string;
  website?: string;
}

/** The registration field keys, used to key form state and errors. */
export type RegistrationField = keyof BusinessRegistration;

/** Response from POST /api/businesses. */
export interface RegisteredBusiness {
  id: string;
  business_name: string;
}

/** Format checks kept identical to the backend (schemas.py) so both agree. */
export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
export const WEBSITE_RE = /^(https?:\/\/)?([\w-]+\.)+[\w-]+(\/\S*)?$/i;
