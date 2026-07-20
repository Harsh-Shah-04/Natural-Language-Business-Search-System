import { useState } from 'react';

import { FilterPanel } from './components/FilterPanel';
import { ResultsList } from './components/ResultsList';
import { SearchBar } from './components/SearchBar';
import { StatusMessage } from './components/StatusMessage';
import { useFilterOptions } from './hooks/useFilterOptions';
import { useSearch } from './hooks/useSearch';
import type { FilterField, SearchFilters } from './types/api';

export default function App() {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<SearchFilters>({});
  const { options } = useFilterOptions();
  const { status, results, submittedQuery, error, search } = useSearch();

  const isLoading = status === 'loading';
  const hasSearched = submittedQuery !== '';

  const handleFilterChange = (field: FilterField, value: string) => {
    const next: SearchFilters = { ...filters, [field]: value || undefined };
    setFilters(next);
    // Narrow the *submitted* query (not whatever is half-typed in the box) so a
    // filter change re-scopes the active results — and only once a search
    // exists to narrow.
    if (hasSearched) search(submittedQuery, next);
  };

  const handleClearFilters = () => {
    const cleared: SearchFilters = {};
    setFilters(cleared);
    if (hasSearched) search(submittedQuery, cleared);
  };

  return (
    <div className="app">
      <header className="app__header">
        <h1 className="app__title">Business Search</h1>
        <p className="app__subtitle">
          Natural-language search across the business directory.
        </p>
      </header>

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

      <main className="app__results">
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
      </main>
    </div>
  );
}
