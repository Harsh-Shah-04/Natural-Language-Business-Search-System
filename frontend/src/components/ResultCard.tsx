import type { MatchedVia, SearchResult } from '../types/api';
import { highlightText } from '../utils/highlight';

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

interface ResultCardProps {
  result: SearchResult;
  /** The submitted query, used to highlight matched terms in the card text. */
  query: string;
}

export function ResultCard({ result, query }: ResultCardProps) {
  const location = formatLocation(result.city, result.state);

  return (
    <article className="result-card">
      <header className="result-card__header">
        <h3 className="result-card__name">
          {highlightText(result.business_name, query)}
        </h3>
        <span
          className={`badge badge--${result.matched_via}`}
          title="How this result matched your query"
        >
          {matchedViaLabel(result.matched_via)}
        </span>
      </header>

      <div className="result-card__meta">
        {result.industry && (
          <span className="badge badge--industry">{result.industry}</span>
        )}
        {result.sub_category && (
          <span className="result-card__subcategory">{result.sub_category}</span>
        )}
        {location && (
          <span className="result-card__location">{location}</span>
        )}
      </div>

      {result.business_description && (
        <p className="result-card__description">
          {highlightText(result.business_description, query)}
        </p>
      )}

      {result.products_services && (
        <div className="result-card__field">
          <span className="result-card__field-label">Products / Services</span>
          <span className="result-card__field-value">
            {highlightText(result.products_services, query)}
          </span>
        </div>
      )}

      <footer className="result-card__footer">
        <span className="result-card__score">
          Relevance <strong>{result.score.toFixed(3)}</strong>
        </span>
      </footer>
    </article>
  );
}
