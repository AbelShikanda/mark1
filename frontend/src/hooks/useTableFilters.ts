import { useMemo, useState } from 'react';

export type FilterOption = { value: string; label: string };

export type FilterDef<T> = {
  key: string;
  label: string;
  /** Case-insensitive text match by default; selects match exactly. */
  type?: 'text' | 'select';
  options?: FilterOption[];
  getValue: (row: T) => string;
  placeholder?: string;
  match?: 'contains' | 'equals';
};

export type TableFiltersResult<T> = {
  search: string;
  setSearch: (value: string) => void;
  values: Record<string, string>;
  setFilter: (key: string, value: string) => void;
  clearFilters: () => void;
  filtered: T[];
  count: number;
  total: number;
  isFiltered: boolean;
  defs: FilterDef<T>[];
};

function normalise(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

/**
 * Shared global-search + per-column filter state.
 *
 * State lives in the calling component, so rows can be replaced by polling
 * (Live page) without resetting the user's filters.
 */
export function useTableFilters<T>(
  rows: T[],
  searchAccessor: (row: T) => string,
  defs: FilterDef<T>[] = [],
  initial: Record<string, string> = {},
): TableFiltersResult<T> {
  const [search, setSearch] = useState('');
  const [values, setValues] = useState<Record<string, string>>(initial);

  const filtered = useMemo(() => {
    const query = normalise(search);
    return rows.filter((row) => {
      if (query && !normalise(searchAccessor(row)).includes(query)) return false;
      for (const def of defs) {
        const wanted = normalise(values[def.key]);
        if (!wanted) continue;
        const actual = normalise(def.getValue(row));
        const mode = def.match ?? (def.type === 'select' ? 'equals' : 'contains');
        if (mode === 'equals' ? actual !== wanted : !actual.includes(wanted)) return false;
      }
      return true;
    });
    // defs are recreated on each render by callers; the filtered row set is
    // what matters for React and these arrays are small dashboard tables.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, search, values]);

  return {
    search,
    setSearch,
    values,
    setFilter: (key, value) => setValues((prev) => ({ ...prev, [key]: value })),
    clearFilters: () => {
      setSearch('');
      setValues({});
    },
    filtered,
    count: filtered.length,
    total: rows.length,
    isFiltered: Boolean(search.trim()) || Object.values(values).some((value) => value.trim()),
    defs,
  };
}
