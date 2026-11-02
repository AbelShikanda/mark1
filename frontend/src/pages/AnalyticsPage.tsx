import { useEffect, useState } from 'react';
import { api } from '../api';

type Recent = { date: string; posts_sent: number; groups_reached: number };

export default function AnalyticsPage() {
  const [summary, setSummary] = useState<{ total_posts: number; recent: Recent[] }>({ total_posts: 0, recent: [] });

  useEffect(() => {
    api.get('/analytics').then((r) => setSummary(r.data));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Analytics</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Total Posts</div>
          <div className="text-3xl font-bold">{summary.total_posts}</div>
        </div>
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Campaigns Run</div>
          <div className="text-3xl font-bold">{summary.recent.length}</div>
        </div>
        <div className="bg-white p-6 rounded-lg border shadow-sm">
          <div className="text-xs text-slate-500 uppercase">Last 7 Days</div>
          <div className="text-3xl font-bold">{summary.recent.reduce((a, b) => a + b.posts_sent, 0)}</div>
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
          {summary.recent.map((r) => (
            <tr key={r.date} className="border-b">
              <td className="p-3">{r.date}</td>
              <td className="p-3">{r.posts_sent}</td>
              <td className="p-3">{r.groups_reached}</td>
            </tr>
          ))}
          {summary.recent.length === 0 && (
            <tr><td colSpan={3} className="p-4 text-center text-slate-400">No analytics yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
