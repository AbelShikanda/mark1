import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';

type Log = { id: number; level: string; message: string; source: string; created_at: string };

export default function LogsPage() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.get<Log[]>('/logs');
      setLogs(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Logs</h1>
        <button onClick={load} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
          Refresh
        </button>
      </div>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Time</th>
            <th className="p-3 border-b">Level</th>
            <th className="p-3 border-b">Source</th>
            <th className="p-3 border-b">Message</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((l) => (
            <tr key={l.id} className="border-b text-sm">
              <td className="p-3 text-slate-500">{l.created_at}</td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded text-xs ${l.level === 'error' ? 'bg-red-100 text-red-700' : l.level === 'warn' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'}`}>
                  {l.level}
                </span>
              </td>
              <td className="p-3 text-slate-600">{l.source}</td>
              <td className="p-3">{l.message}</td>
            </tr>
          ))}
          {logs.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-center text-slate-400">No logs yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
