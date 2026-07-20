interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
}

/** Query input + button. Enter submits (it's a real <form>). */
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
      <input
        className="search-bar__input"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search businesses, e.g. “eco-friendly packaging for restaurants”"
        aria-label="Search query"
        autoFocus
      />
      <button
        className="search-bar__button"
        type="submit"
        disabled={loading || value.trim() === ''}
      >
        {loading ? 'Searching…' : 'Search'}
      </button>
    </form>
  );
}
