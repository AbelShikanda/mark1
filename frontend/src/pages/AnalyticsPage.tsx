import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <button onClick={load} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
          Refresh
        </button>
      </div>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Total Posts</div>
          <div className="text-3xl font-bold">{summary.total_posts}</div>
        </div>
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Campaigns Run</div>
          <div className="text-3xl font-bold">{summary.campaigns_run}</div>
        </div>
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Groups Reached</div>
          <div className="text-3xl font-bold">{summary.total_groups_reached}</div>
        </div>
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Last 7 Days</div>
          <div className="text-3xl font-bold">{last7Days}</div>
        </div>
      </div>

      <table className="w-full border-collapse border border-slate-200 rounded-lg mt-4">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Date</th>
            <th className="p-3 border-b">Posts Sent</th>
            <th className="p-3 border-b">Groups Reached</th>
          </tr>
        </thead>
        <tbody>
          {recent.map((day) => (
            <tr key={day.date} className="border-b">
              <td className="p-3">{day.date}</td>
              <td className="p-3">{day.posts_sent}</td>
              <td className="p-3">{day.groups_reached}</td>
            </tr>
          ))}
          {recent.length === 0 && (
            <tr><td colSpan={3} className="p-4 text-center text-slate-400">No analytics yet. Run a campaign to see results here.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
