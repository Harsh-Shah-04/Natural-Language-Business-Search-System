import { useEffect, useState } from 'react';

import { FilterPanel } from '../components/FilterPanel';
import { IntentPanel } from '../components/IntentPanel';
import { ResultsList } from '../components/ResultsList';
import { SearchBar } from '../components/SearchBar';
import { StatusMessage } from '../components/StatusMessage';
import { useFilterOptions } from '../hooks/useFilterOptions';
import { useSearch } from '../hooks/useSearch';
import type { FilterField, SearchFilters } from '../types/api';

interface SearchPageProps {
  /** Set by the app shell to run a search on demand (e.g. right after a
   *  business is registered). The nonce makes repeated identical queries
   *  re-trigger. */
  trigger?: { query: string; nonce: number } | null;
  /** Bumped by the shell after a successful registration so City / Industry /
   *  etc. dropdowns pick up newly introduced values without a page refresh. */
  filtersRefreshNonce?: number;
}

export function SearchPage({ trigger, filtersRefreshNonce = 0 }: SearchPageProps) {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>({});
  const { options, reload: reloadFilterOptions } = useFilterOptions();
  const { status, results, intent, submittedQuery, error, search } = useSearch();

  const isLoading = status === 'loading';
  const hasSearched = submittedQuery !== '';

  // Run a search when the shell hands one in (post-registration "search this
  // business"). Clears filters so the new business isn't filtered out.
  useEffect(() => {
    if (trigger && trigger.query.trim() !== '') {
      setQuery(trigger.query);
      setFilters({});
      search(trigger.query, {});
    }
  }, [trigger, search]);

  // Refetch filter allow-list after registration. Nonce 0 is the idle value;
  // only positive bumps (from App) trigger a reload beyond the mount fetch.
  useEffect(() => {
    if (filtersRefreshNonce > 0) {
      void reloadFilterOptions();
    }
  }, [filtersRefreshNonce, reloadFilterOptions]);

  const handleFilterChange = (field: FilterField, value: string) => {
    const next: SearchFilters = { ...filters, [field]: value || undefined };
    setFilters(next);
    if (hasSearched) search(submittedQuery, next);
  };

  const handleClearFilters = () => {
    const cleared: SearchFilters = {};
    setFilters(cleared);
    if (hasSearched) search(submittedQuery, cleared);
  };

  return (
    <>
      <div className="app__controls">
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={() => search(query, filters)}
          loading={isLoading}
        />
        <FilterPanel
          filters={filters}
          options={options}
          onChange={handleFilterChange}
          onClear={handleClearFilters}
          disabled={isLoading}
        />
      </div>

      <div className="app__results">
        {status === 'idle' && (
          <StatusMessage
            variant="idle"
            title="Search the directory"
            detail="Type a query above and press Enter to see matching businesses."
          />
        )}

        {status === 'loading' && (
          <StatusMessage variant="loading" title="Searching…" />
        )}

        {status === 'error' && (
          <StatusMessage
            variant="error"
            title="Search failed"
            detail={error ?? undefined}
          />
        )}

        {/* Above the results, and outside the results-length check: what the
            system understood is worth showing even when nothing matched — that
            pairing is exactly how a user tells "misread me" from "has no such
            business". Absent whenever the backend returned no intent. */}
        {status === 'success' && intent && <IntentPanel intent={intent} />}

        {status === 'success' &&
          (results.length > 0 ? (
            <ResultsList results={results} />
          ) : (
            <StatusMessage
              variant="empty"
              title="No results found"
              detail={`Nothing matched “${submittedQuery}”. Try different words or clear the filters.`}
            />
          ))}
      </div>
    </>
  );
}
