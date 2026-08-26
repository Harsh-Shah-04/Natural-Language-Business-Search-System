import { useCallback, useRef, useState } from 'react';

import { ApiError } from '../api/client';
import { searchBusinesses } from '../api/search';
import type { QueryIntent, SearchFilters, SearchResult } from '../types/api';

export type SearchStatus = 'idle' | 'loading' | 'success' | 'error';

interface SearchState {
  status: SearchStatus;
  results: SearchResult[];
  /**
   * What the backend understood the query to mean, or null when it had no
   * opinion. Held alongside the results it was inferred for, so a stale intent
   * can never be shown next to fresh results.
   */
  intent: QueryIntent | null;
  /** The query string that produced the current results (for empty-state copy). */
  submittedQuery: string;
  error: string | null;
}

const INITIAL: SearchState = {
  status: 'idle',
  results: [],
  intent: null,
  submittedQuery: '',
  error: null,
};

/**
 * Owns the search request lifecycle: idle -> loading -> success | error.
 * A monotonic request counter guards against a slow earlier request landing
 * after a faster later one (last submission wins).
 */
export function useSearch() {
  const [state, setState] = useState<SearchState>(INITIAL);
  const latestRequest = useRef(0);

  const search = useCallback(async (query: string, filters: SearchFilters) => {
    const trimmed = query.trim();
    if (!trimmed) return;

    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    setState((prev) => ({ ...prev, status: 'loading', error: null }));

    try {
      const response = await searchBusinesses(trimmed, filters);
      if (requestId !== latestRequest.current) return; // superseded
      setState({
        status: 'success',
        results: response.results,
        // Tolerate a backend that predates M6.1 (or has the intent layer
        // disabled): `intent` is simply absent, and the panel does not render.
        intent: response.intent ?? null,
        submittedQuery: trimmed,
        error: null,
      });
    } catch (err) {
      if (requestId !== latestRequest.current) return; // superseded
      const message =
        err instanceof ApiError
          ? err.message
          : 'Something went wrong while searching. Please try again.';
      setState((prev) => ({ ...prev, status: 'error', error: message }));
    }
  }, []);

  return { ...state, search };
}
