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

interface ResultCardProps {
  result: SearchResult;
}

/**
 * Card text is rendered plain. Query terms were previously marked in yellow,
 * which was removed deliberately: the highlighting matched the raw query
 * literally, independent of how the result was actually retrieved, so a
 * document found purely by vector similarity still showed literal term marks
 * next to a "Semantic" badge. On this corpus the effect was actively
 * misleading — the templated descriptions mean a query containing "business"
 * marked that word in 120 of 120 documents, painting the least discriminative
 * word in the dataset onto every result. `matched_via` (the badge) is the
 * honest signal for how a result matched; see backend _reciprocal_rank_fusion.
 */
export function ResultCard({ result }: ResultCardProps) {
  const location = formatLocation(result.city, result.state);

  return (
    <article className="result-card">
      <header className="result-card__header">
        <h3 className="result-card__name">{result.business_name}</h3>
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
        <p className="result-card__description">{result.business_description}</p>
      )}

      {result.products_services && (
        <div className="result-card__field">
          <span className="result-card__field-label">Products / Services</span>
          <span className="result-card__field-value">{result.products_services}</span>
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
