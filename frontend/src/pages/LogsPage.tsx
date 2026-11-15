import { useEffect, useMemo, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { BTN_SECONDARY } from '../ui';

type Log = { id: number; level: string; message: string; source: string; created_at: string };

const LIMITS = [50, 100, 250, 500];

const LEVEL_STYLES: Record<string, string> = {
  error: 'bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-300',
  warning: 'bg-yellow-100 text-yellow-700 dark:bg-amber-950/60 dark:text-amber-300',
  warn: 'bg-yellow-100 text-yellow-700 dark:bg-amber-950/60 dark:text-amber-300',
  info: 'bg-green-100 text-green-700 dark:bg-emerald-950/60 dark:text-emerald-300',
};

const DATE_INPUT =
  'rounded border border-slate-300 bg-white p-2 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100';

export default function LogsPage() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [limit, setLimit] = useState(50);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = async (nextLimit = limit) => {
    try {
      const res = await api.get<Log[]>('/logs', { params: { limit: nextLimit } });
      setLogs(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load(limit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit]);

  const inRange = (log: Log): boolean => {
    const day = (log.created_at ?? '').slice(0, 10);
    if (fromDate && day < fromDate) return false;
    if (toDate && day > toDate) return false;
    return true;
  };

  const dateFiltered = useMemo(
    () => logs.filter(inRange),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [logs, fromDate, toDate],
  );

  const levelOptions = useMemo(
    () =>
      Array.from(new Set(logs.map((log) => log.level).filter(Boolean)))
        .sort((a, b) => a.localeCompare(b))
        .map((value) => ({ value, label: value })),
    [logs],
  );

  const table = useTableFilters<Log>(
    dateFiltered,
    (log) => `${log.message} ${log.source} ${log.level} ${log.created_at}`,
    [
      { key: 'time', label: 'Time', getValue: (log) => log.created_at },
      { key: 'level', label: 'Level', type: 'select', options: levelOptions, getValue: (log) => log.level },
      { key: 'source', label: 'Source', getValue: (log) => log.source },
      { key: 'message', label: 'Message', getValue: (log) => log.message },
    ],
  );

  const isFiltered = table.isFiltered || Boolean(fromDate) || Boolean(toDate);

  const clearAll = () => {
    table.clearFilters();
    setFromDate('');
    setToDate('');
  };

  const columns: DataTableColumn<Log>[] = [
    {
      key: 'time',
      header: 'Time',
      filter: { type: 'text', placeholder: 'Filter time' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (log) => log.created_at,
    },
    {
      key: 'level',
      header: 'Level',
      filter: { type: 'select', options: levelOptions, placeholder: 'All levels' },
      cell: (log) => (
        <span className={`rounded px-2 py-1 text-xs ${LEVEL_STYLES[log.level] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
          {log.level}
        </span>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      filter: { type: 'text' },
      cellClassName: 'text-xs text-slate-600 dark:text-slate-300',
      cell: (log) => log.source,
    },
    {
      key: 'message',
      header: 'Message',
      filter: { type: 'text' },
      cell: (log) => log.message,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Logs</h1>
        <button onClick={() => load(limit)} className={BTN_SECONDARY}>
          Refresh
        </button>
      </div>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <TableToolbar
        search={table.search}
        onSearch={table.setSearch}
        placeholder="Search message or source"
        count={table.count}
        total={table.total}
        onClear={clearAll}
        isFiltered={isFiltered}
      >
        <label className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
          Limit
          <select
            className={DATE_INPUT}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            aria-label="Number of log entries to load"
          >
            {LIMITS.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
          From
          <input
            type="date"
            className={DATE_INPUT}
            value={fromDate}
            max={toDate || undefined}
            onChange={(event) => setFromDate(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
          To
          <input
            type="date"
            className={DATE_INPUT}
            value={toDate}
            min={fromDate || undefined}
            onChange={(event) => setToDate(event.target.value)}
          />
        </label>
      </TableToolbar>

      <DataTable
        columns={columns}
        rows={table.filtered}
        rowKey={(log) => log.id}
        filters={table.values}
        onFilterChange={table.setFilter}
        emptyMessage={logs.length === 0 ? 'No logs yet.' : 'No logs match the current filters.'}
      />
    </div>
  );
}
