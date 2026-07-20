type Variant = 'loading' | 'empty' | 'error' | 'idle';

interface StatusMessageProps {
  variant: Variant;
  title: string;
  detail?: string;
}

/** Inline SVG icon per state — no icon dependency. */
function StateIcon({ variant }: { variant: Variant }) {
  if (variant === 'loading') {
    return <span className="status-message__spinner" aria-hidden="true" />;
  }

  const paths: Record<Exclude<Variant, 'loading'>, string> = {
    idle: 'm21 21-4.3-4.3M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Z',
    empty: 'M3 7h18M3 12h18M3 17h10', // stacked lines = an empty list
    error: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  };

  return (
    <svg
      className="status-message__icon"
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
        d={paths[variant]}
      />
    </svg>
  );
}

/** Full-width centred card for the non-results states. */
export function StatusMessage({ variant, title, detail }: StatusMessageProps) {
  return (
    <div
      className={`status-message status-message--${variant}`}
      role={variant === 'error' ? 'alert' : 'status'}
      aria-live={variant === 'error' ? 'assertive' : 'polite'}
    >
      <StateIcon variant={variant} />
      <p className="status-message__title">{title}</p>
      {detail && <p className="status-message__detail">{detail}</p>}
    </div>
  );
}
