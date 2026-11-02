import { useEffect, useState } from 'react';
import { api } from '../api';

type Group = { id: number; name: string; url: string | null; category: string | null };

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<Group[]>('/groups').then((r) => setGroups(r.data));
  }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const created = await api.post<Group>('/groups', { name, category });
    setGroups([created.data, ...groups]);
    setName(''); setCategory('');
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Groups</h1>
      <form onSubmit={add} className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-lg">
        <input
          className="border rounded p-2"
          placeholder="Group name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="border rounded p-2"
          placeholder="Category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
        <button
          className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
          disabled={loading || !name}
        >
          + Add
        </button>
      </form>
      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Name</th>
            <th className="p-3 border-b">Category</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.id} className="border-b">
              <td className="p-3">{g.name}</td>
              <td className="p-3 text-slate-500 text-xs">{g.category ?? '-'}</td>
            </tr>
          ))}
          {groups.length === 0 && (
            <tr><td colSpan={2} className="p-4 text-center text-slate-400">No groups yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
