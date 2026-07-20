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

/** Response body from POST /api/search. */
export interface SearchResponse {
  query: string;
  results: SearchResult[];
  filters: SearchFilters | null;
}

/**
 * Response from GET /api/filters/values: each filterable field mapped to its
 * allowed values (the backend derives these from the live DB and sorts them).
 */
export type FilterValues = Record<FilterField, string[]>;
