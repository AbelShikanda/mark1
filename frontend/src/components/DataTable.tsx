import type { ReactNode } from 'react';
import {
  EMPTY_CELL,
  FILTER_INPUT,
  FILTER_TH,
  ROW,
  TABLE,
  TABLE_WRAP,
  TD,
  TH,
} from '../ui';

export type TableFilterControl =
  | { type: 'text'; placeholder?: string }
  | {
      type: 'select';
      placeholder?: string;
      options: { value: string; label: string }[];
    };

export type DataTableColumn<T> = {
  key: string;
  header: string;
  cell: (row: T) => ReactNode;
  filter?: TableFilterControl;
  headerClassName?: string;
  cellClassName?: string;
};

export function TableToolbar({
  search,
  onSearch,
  placeholder = 'Search…',
  count,
  total,
  onClear,
  isFiltered,
  children,
}: {
  search: string;
  onSearch: (value: string) => void;
  placeholder?: string;
  count: number;
  total: number;
  onClear: () => void;
  isFiltered: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <input
        className="w-full rounded border border-slate-300 bg-white p-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500 sm:max-w-sm"
        placeholder={placeholder}
        value={search}
        onChange={(event) => onSearch(event.target.value)}
        aria-label={placeholder}
      />
      {children}
      <button
        type="button"
        onClick={onClear}
        disabled={!isFiltered}
        className="rounded border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
      >
        Clear filters
      </button>
      <span className="text-xs text-slate-500 dark:text-slate-400">
        Showing {count} of {total}
      </span>
    </div>
  );
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  filters,
  onFilterChange,
  emptyMessage,
  maxHeight = 'max-h-[65vh]',
  minWidth,
  rowClassName,
}: {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  filters: Record<string, string>;
  onFilterChange: (key: string, value: string) => void;
  emptyMessage: string;
  maxHeight?: string;
  minWidth?: string;
  rowClassName?: (row: T) => string;
}) {
  return (
    <div className={`${TABLE_WRAP} ${maxHeight}`}>
      <table className={TABLE} style={minWidth ? { minWidth } : undefined}>
        <thead className="bg-slate-100 dark:bg-slate-800">
          <tr className="text-left text-xs uppercase tracking-wide text-slate-500 dark:text-slate-300">
            {columns.map((column) => (
              <th
                key={column.key}
                className={`${TH} ${column.headerClassName ?? ''}`}
                scope="col"
              >
                {column.header}
              </th>
            ))}
          </tr>
          <tr className="bg-slate-50 dark:bg-slate-800/95">
            {columns.map((column) => (
              <th key={column.key} className={FILTER_TH} scope="col">
                {column.filter?.type === 'text' && (
                  <input
                    className={FILTER_INPUT}
                    placeholder={column.filter.placeholder ?? `Filter ${column.header.toLowerCase()}`}
                    value={filters[column.key] ?? ''}
                    onChange={(event) => onFilterChange(column.key, event.target.value)}
                    aria-label={`Filter by ${column.header}`}
                  />
                )}
                {column.filter?.type === 'select' && (
                  <select
                    className={FILTER_INPUT}
                    value={filters[column.key] ?? ''}
                    onChange={(event) => onFilterChange(column.key, event.target.value)}
                    aria-label={`Filter by ${column.header}`}
                  >
                    <option value="">{column.filter.placeholder ?? 'All'}</option>
                    {column.filter.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className={`${ROW} ${rowClassName?.(row) ?? ''}`}>
              {columns.map((column) => (
                <td key={column.key} className={`${TD} ${column.cellClassName ?? ''}`}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className={EMPTY_CELL}>
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
