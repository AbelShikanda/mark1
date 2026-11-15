import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { BTN_SECONDARY, CARD_PAD, MUTED, SUBTLE } from '../ui';

type Recent = { date: string; posts_sent: number; groups_reached: number };

type Summary = {
  total_posts: number;
  total_groups_reached: number;
  campaigns_run: number;
  recent: Recent[];
};

const emptySummary: Summary = { total_posts: 0, total_groups_reached: 0, campaigns_run: 0, recent: [] };

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.get<Summary>('/analytics');
      const data = res.data ?? emptySummary;
      setSummary({
        total_posts: typeof data.total_posts === 'number' ? data.total_posts : 0,
        total_groups_reached: typeof data.total_groups_reached === 'number' ? data.total_groups_reached : 0,
        campaigns_run: typeof data.campaigns_run === 'number' ? data.campaigns_run : 0,
        recent: Array.isArray(data.recent) ? data.recent : [],
      });
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const recent = summary.recent;
  const last7Days = recent.reduce((total, day) => total + (day.posts_sent || 0), 0);
  const table = useTableFilters<Recent>(
    recent,
    (day) => `${day.date} ${day.posts_sent} ${day.groups_reached}`,
    [
      { key: 'date', label: 'Date', getValue: (day) => day.date },
      { key: 'posts', label: 'Posts sent', getValue: (day) => String(day.posts_sent) },
      { key: 'groups', label: 'Groups reached', getValue: (day) => String(day.groups_reached) },
    ],
  );

  const columns: DataTableColumn<Recent>[] = [
    { key: 'date', header: 'Date', filter: { type: 'text' }, cell: (day) => day.date },
    { key: 'posts', header: 'Posts Sent', filter: { type: 'text' }, cell: (day) => day.posts_sent },
    { key: 'groups', header: 'Groups Reached', filter: { type: 'text' }, cell: (day) => day.groups_reached },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <button onClick={load} className={BTN_SECONDARY}>
          Refresh
        </button>
      </div>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className={`${CARD_PAD} p-6`}>
          <div className={`text-xs uppercase ${MUTED}`}>Total Posts</div>
          <div className="text-3xl font-bold">{summary.total_posts}</div>
        </div>
        <div className={`${CARD_PAD} p-6`}>
          <div className={`text-xs uppercase ${MUTED}`}>Campaigns Run</div>
          <div className="text-3xl font-bold">{summary.campaigns_run}</div>
        </div>
        <div className={`${CARD_PAD} p-6`}>
          <div className={`text-xs uppercase ${MUTED}`}>Groups Reached</div>
          <div className="text-3xl font-bold">{summary.total_groups_reached}</div>
        </div>
        <div className={`${CARD_PAD} p-6`}>
          <div className={`text-xs uppercase ${MUTED}`}>Last 7 Days</div>
          <div className="text-3xl font-bold">{last7Days}</div>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <h2 className="text-lg font-semibold">Recent analytics</h2>
        <TableToolbar
          search={table.search}
          onSearch={table.setSearch}
          placeholder="Search date, posts or groups"
          count={table.count}
          total={table.total}
          onClear={table.clearFilters}
          isFiltered={table.isFiltered}
        />
        <div className={`text-xs ${SUBTLE}`}>Filters apply to the recent days table.</div>
      </div>

      <DataTable
        columns={columns}
        rows={table.filtered}
        rowKey={(day) => day.date}
        filters={table.values}
        onFilterChange={table.setFilter}
        emptyMessage={recent.length === 0 ? 'No analytics yet. Run a campaign to see results here.' : 'No analytics rows match the current filters.'}
      />
    </div>
  );
}
