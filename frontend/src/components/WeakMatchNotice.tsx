import type { QueryIntent, SearchResult } from '../types/api';

/**
 * True when the result set is nearest-neighbour noise rather than a match.
 *
 * Vector search has no relevance floor: it returns the k nearest documents
 * however far away they are, and cannot return "nothing". So a query the
 * directory has no answer for -- "washing powder", a person's name -- still
 * renders ten confident-looking cards. Two signals together identify it:
 *
 *  - the backend returned no intent, i.e. the query mapped to nothing in the
 *    trusted taxonomy, and
 *  - not one result matched a keyword, so only the embedding contributed.
 *
 * Either signal alone is normal and must not trigger this. A situational
 * query ("our site crashes during a sale") legitimately shares no keyword
 * with the businesses it should find, and a bare word like "blue" matches
 * business names via keyword while producing no intent.
 *
 * This does not catch everything. Gibberish that the embedding classifier
 * still maps to some taxonomy entry produces an intent, so it passes this
 * check -- measured on "asdkjhaslkdjh", which reranks to a plausible-looking
 * score. This narrows the failure, it does not close it.
 */
export function isWeakMatch(
  results: SearchResult[],
  intent: QueryIntent | null,
): boolean {
  if (intent !== null) return false;
  if (results.length === 0) return false;
  return results.every((result) => result.matched_via === 'semantic');
}

/**
 * Shown above the results, not instead of them: the nearest match is
 * occasionally what the user meant, so this qualifies the list rather than
 * hiding it. Display-only -- retrieval, RRF and reranking are untouched.
 */
export function WeakMatchNotice() {
  return (
    <div className="weak-match" role="status" aria-live="polite">
      <svg
        className="weak-match__icon"
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
      >
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v4m0 4h.01M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z"
        />
      </svg>
      <p className="weak-match__text">
        <strong>No strong match in the directory.</strong> Nothing here matched
        your wording directly, so these are simply the closest entries. Try
        naming the service you need, or a different description.
      </p>
    </div>
  );
}
