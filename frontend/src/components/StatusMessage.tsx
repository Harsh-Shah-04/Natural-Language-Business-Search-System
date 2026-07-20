type Variant = 'loading' | 'empty' | 'error' | 'idle';

interface StatusMessageProps {
  variant: Variant;
  title: string;
  detail?: string;
}

/** Full-width centred message for the non-results states. */
export function StatusMessage({ variant, title, detail }: StatusMessageProps) {
  return (
    <div className={`status-message status-message--${variant}`} role="status">
      {variant === 'loading' && (
        <span className="status-message__spinner" aria-hidden="true" />
      )}
      <p className="status-message__title">{title}</p>
      {detail && <p className="status-message__detail">{detail}</p>}
    </div>
  );
}
