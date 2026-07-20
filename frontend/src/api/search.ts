// Endpoint functions for the search API. One function per backend route,
// each typed against the shared API contract in ../types/api.

import type {
  FilterValues,
  SearchFilters,
  SearchRequest,
  SearchResponse,
} from '../types/api';
import { apiClient } from './client';

/** Drop empty/undefined filter values so we only send the ones actually set. */
function compactFilters(filters: SearchFilters): SearchFilters | null {
  const entries = Object.entries(filters).filter(
    ([, value]) => value != null && value !== '',
  );
  return entries.length > 0 ? (Object.fromEntries(entries) as SearchFilters) : null;
}

/** POST /api/search — run a search, optionally narrowed by filters. */
export function searchBusinesses(
  query: string,
  filters: SearchFilters = {},
  limit = 10,
): Promise<SearchResponse> {
  const body: SearchRequest = {
    query,
    limit,
    filters: compactFilters(filters),
  };
  return apiClient.request<SearchResponse>('/api/search', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** GET /api/filters/values — the allowed values for each filter dropdown. */
export function getFilterValues(): Promise<FilterValues> {
  return apiClient.request<FilterValues>('/api/filters/values');
}
