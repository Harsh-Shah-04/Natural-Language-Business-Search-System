import type { SearchResult } from '../types/api';
import { ResultCard } from './ResultCard';

interface ResultsListProps {
  results: SearchResult[];
  /** Submitted query, passed to cards for keyword highlighting. */
  query: string;
}

/** Responsive grid of result cards. */
export function ResultsList({ results, query }: ResultsListProps) {
  return (
    <section className="results-list" aria-label="Search results">
      <p className="results-list__count">
        {results.length} {results.length === 1 ? 'result' : 'results'}
      </p>
      <div className="results-list__grid">
        {results.map((result) => (
          <ResultCard key={result.id} result={result} query={query} />
        ))}
      </div>
    </section>
  );
}
