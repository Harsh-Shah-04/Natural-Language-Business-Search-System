import type { IntentSource, QueryIntent } from '../types/api';

interface IntentPanelProps {
  intent: QueryIntent;
}

/**
 * How each provider is described to the user. Provenance is shown, not hidden:
 * a checked-in fixture and a real inference must not look alike, or the panel
 * becomes a way to make the system seem to understand more than it does —
 * which is the exact problem this feature exists to fix.
 */
const SOURCE_LABELS: Record<string, string> = {
  'embedding-taxonomy': 'matched against the service taxonomy',
  fixture: 'demo fixture — not inferred',
  llm: 'interpreted by a language model',
};

function sourceLabel(source: IntentSource): string {
  return SOURCE_LABELS[source] ?? source;
}

/**
 * "I understood you need…" — the system's reading of the query, shown above
 * the results.
 *
 * Rendered only when the backend returns a non-null `intent`. A query the
 * intent layer cannot place produces no panel at all rather than a low-
 * confidence guess, so the presence of this panel is itself a signal.
 */
export function IntentPanel({ intent }: IntentPanelProps) {
  const { underlying_need, service_categories, exclusions, confidence, source } = intent;

  return (
    <section className="intent-panel" aria-label="Interpreted intent">
      <div className="intent-panel__head">
        <svg
          className="intent-panel__icon"
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
            d="M12 3a6 6 0 0 0-3.6 10.8c.5.4.8 1 .9 1.6l.1.6h5.2l.1-.6c.1-.6.4-1.2.9-1.6A6 6 0 0 0 12 3ZM9.5 20h5"
          />
        </svg>
        <p className="intent-panel__label">I understood you need</p>
      </div>

      <p className="intent-panel__need">{underlying_need}</p>

      {service_categories.length > 0 && (
        <ul className="intent-panel__categories" aria-label="Inferred service categories">
          {service_categories.map((category) => (
            <li key={category} className="intent-panel__category">
              {category}
            </li>
          ))}
        </ul>
      )}

      {exclusions.length > 0 && (
        <p className="intent-panel__exclusions">
          Excluding: {exclusions.join(', ')}
        </p>
      )}

      <p className="intent-panel__provenance">
        {sourceLabel(source)} · confidence {confidence.toFixed(2)}
      </p>
    </section>
  );
}
