import type { FilterField, FilterValues, SearchFilters } from '../types/api';
import { FILTER_FIELDS, FILTER_LABELS } from '../types/api';
import { FilterSelect } from './FilterSelect';

interface FilterPanelProps {
  filters: SearchFilters;
  options: FilterValues;
  onChange: (field: FilterField, value: string) => void;
  onClear: () => void;
  disabled?: boolean;
}

/** The row of filter dropdowns plus a "clear" action when any is active. */
export function FilterPanel({
  filters,
  options,
  onChange,
  onClear,
  disabled,
}: FilterPanelProps) {
  const hasActiveFilter = FILTER_FIELDS.some((field) => filters[field]);

  return (
    <section className="filter-panel" aria-label="Filters">
      <div className="filter-panel__grid">
        {FILTER_FIELDS.map((field) => (
          <FilterSelect
            key={field}
            label={FILTER_LABELS[field]}
            value={filters[field] ?? ''}
            options={options[field]}
            onChange={(value) => onChange(field, value)}
            disabled={disabled}
          />
        ))}
      </div>
      {hasActiveFilter && (
        <button
          type="button"
          className="filter-panel__clear"
          onClick={onClear}
          disabled={disabled}
        >
          Clear filters
        </button>
      )}
    </section>
  );
}
