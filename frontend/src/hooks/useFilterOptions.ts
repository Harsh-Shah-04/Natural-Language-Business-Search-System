import { useEffect, useState } from 'react';

import { getFilterValues } from '../api/search';
import type { FilterValues } from '../types/api';
import { FILTER_FIELDS } from '../types/api';

const EMPTY_OPTIONS: FilterValues = {
  industry: [],
  city: [],
  state: [],
  nature: [],
  sub_category: [],
};

/**
 * Loads the allowed values for the filter dropdowns once on mount.
 * Failure is non-fatal: the dropdowns simply stay empty (and hidden) rather
 * than blocking search — the core flow is typing a query.
 */
export function useFilterOptions() {
  const [options, setOptions] = useState<FilterValues>(EMPTY_OPTIONS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getFilterValues()
      .then((values) => {
        if (!active) return;
        // Defensively fill any field the backend might omit, so consumers can
        // always index every FilterField.
        const merged = { ...EMPTY_OPTIONS };
        for (const field of FILTER_FIELDS) {
          if (Array.isArray(values[field])) merged[field] = values[field];
        }
        setOptions(merged);
      })
      .catch(() => {
        // Leave options empty; the panel renders nothing usable but search works.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return { options, loading };
}
