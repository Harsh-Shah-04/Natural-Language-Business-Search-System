interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

/** Query input (with a search icon) + button. Enter submits (it's a real form). */
export function SearchBar({ value, onChange, onSubmit, loading }: SearchBarProps) {
  return (
    <form
      className="search-bar"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      role="search"
    >
      <div className="search-bar__field">
        <svg
          className="search-bar__icon"
          viewBox="0 0 24 24"
          aria-hidden="true"
          focusable="false"
        >
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            d="m21 21-4.3-4.3M11 19a8 8 0 1 1 0-16 8 8 0 0 1 0 16Z"
          />
        </svg>
        <input
          className="search-bar__input"
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Search businesses, e.g. “eco-friendly packaging for restaurants”"
          aria-label="Search query"
          autoFocus
        />
      </div>
      <button
        className="search-bar__button"
        type="submit"
        disabled={loading || value.trim() === ''}
      >
        {loading && <span className="search-bar__spinner" aria-hidden="true" />}
        {loading ? 'Searching…' : 'Search'}
      </button>
    </form>
  );
}
