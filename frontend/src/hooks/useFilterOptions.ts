import { useCallback, useEffect, useState } from 'react';

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

function mergeFilterValues(values: FilterValues): FilterValues {
  // Defensively fill any field the backend might omit, so consumers can
  // always index every FilterField.
  const merged = { ...EMPTY_OPTIONS };
  for (const field of FILTER_FIELDS) {
    if (Array.isArray(values[field])) merged[field] = values[field];
  }
  return merged;
}

/**
 * Loads the allowed values for the filter dropdowns on mount.
 * Exposes `reload` so a successful registration can refresh the lists
 * without a full page remount (Search stays mounted while Register is shown).
 * Failure is non-fatal: the dropdowns simply stay empty (and hidden) rather
 * than blocking search — the core flow is typing a query.
 */
export function useFilterOptions() {
  const [options, setOptions] = useState<FilterValues>(EMPTY_OPTIONS);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const values = await getFilterValues();
      setOptions(mergeFilterValues(values));
    } catch {
      // Keep whatever options we already have; search still works without
      // an updated allow-list until the next successful reload.
    }
  }, []);

  useEffect(() => {
    let active = true;
    getFilterValues()
      .then((values) => {
        if (!active) return;
        setOptions(mergeFilterValues(values));
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

  return { options, loading, reload };
}
