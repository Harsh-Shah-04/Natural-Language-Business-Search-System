import type { MatchedVia, SearchResult } from '../types/api';

/** Turn matched_via into display copy. Backend sends semantic | keyword | both. */
function matchedViaLabel(matchedVia: MatchedVia): string {
  switch (matchedVia) {
    case 'semantic':
      return 'Semantic';
    case 'keyword':
      return 'Keyword';
    case 'both':
      return 'Semantic + Keyword';
    default:
      return matchedVia;
  }
}

/** Join city and state into "City, State", tolerating either being missing. */
function formatLocation(city: string | null, state: string | null): string {
  return [city, state].filter(Boolean).join(', ');
}

export function ResultCard({ result }: { result: SearchResult }) {
  const location = formatLocation(result.city, result.state);

  return (
    <article className="result-card">
      <header className="result-card__header">
        <h3 className="result-card__name">{result.business_name}</h3>
        <span
          className={`result-card__match result-card__match--${result.matched_via}`}
        >
          {matchedViaLabel(result.matched_via)}
        </span>
      </header>

      <div className="result-card__meta">
        {result.industry && <span className="tag">{result.industry}</span>}
        {result.sub_category && (
          <span className="tag tag--muted">{result.sub_category}</span>
        )}
        {location && <span className="result-card__location">{location}</span>}
      </div>

      {result.business_description && (
        <p className="result-card__description">{result.business_description}</p>
      )}

      {result.products_services && (
        <div className="result-card__field">
          <span className="result-card__field-label">Products / Services</span>
          <span className="result-card__field-value">
            {result.products_services}
          </span>
        </div>
      )}

      <footer className="result-card__footer">
        <span className="result-card__score">
          Score <strong>{result.score.toFixed(3)}</strong>
        </span>
      </footer>
    </article>
  );
}
