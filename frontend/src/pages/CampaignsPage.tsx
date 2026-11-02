import { useEffect, useState } from 'react';
import { api } from '../api';

type Campaign = { id: number; name: string; status: string; posts_sent: number; created_at: string };
type Product = { id: number; name: string };
type Group = { id: number; name: string };

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [name, setName] = useState('');
  const [selProd, setSelProd] = useState<number[]>([]);
  const [selGrp, setSelGrp] = useState<number[]>([]);

  useEffect(() => {
    Promise.all([
      api.get<Campaign[]>('/campaigns').then((r) => setCampaigns(r.data)),
      api.get<Product[]>('/products').then((r) => setProducts(r.data)),
      api.get<Group[]>('/groups').then((r) => setGroups(r.data)),
    ]);
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post<Campaign>('/campaigns', { name, product_ids: selProd, group_ids: selGrp });
    setName('');
    window.location.reload();
  };

  const start = async (id: number) => {
    await api.post(`/campaigns/${id}/start`);
    window.location.reload();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Campaigns</h1>
      <form onSubmit={create} className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-xl bg-white p-4 rounded-lg border">
        <input
          className="border rounded p-2"
          placeholder="Campaign name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <div>
          <label className="block text-xs text-slate-500 mb-1">Products</label>
          <div className="border rounded p-2 max-h-24 overflow-y-auto text-sm">
            {products.map((p) => (
              <label key={p.id} className="flex items-center gap-2 cursor-pointer hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={selProd.includes(p.id)}
                  onChange={() => setSelProd(selProd.includes(p.id) ? selProd.filter((i) => i !== p.id) : [...selProd, p.id])}
                />
                {p.name}
              </label>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Groups</label>
          <div className="border rounded p-2 max-h-24 overflow-y-auto text-sm">
            {groups.map((g) => (
              <label key={g.id} className="flex items-center gap-2 cursor-pointer hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={selGrp.includes(g.id)}
                  onChange={() => setSelGrp(selGrp.includes(g.id) ? selGrp.filter((i) => i !== g.id) : [...selGrp, g.id])}
                />
                {g.name}
              </label>
            ))}
          </div>
        </div>
        <button
          className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 col-span-3 md:col-span-1 mt-2 md:mt-0"
          disabled={!name || selProd.length === 0 || selGrp.length === 0}
        >
          + Create Campaign
        </button>
      </form>
      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Name</th>
            <th className="p-3 border-b">Status</th>
            <th className="p-3 border-b">Posts Sent</th>
            <th className="p-3 border-b">Action</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr key={c.id} className="border-b">
              <td className="p-3">{c.name}</td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded text-xs ${c.status === 'completed' ? 'bg-green-100 text-green-700' : c.status === 'running' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'}`}>
                  {c.status}
                </span>
              </td>
              <td className="p-3">{c.posts_sent}</td>
              <td className="p-3">
                {c.status === 'idle' ? (
                  <button
                    className="text-indigo-600 hover:underline text-xs"
                    onClick={() => start(c.id)}
                  >
                    ▶ Start
                  </button>
                ) : (
                  <span className="text-xs text-slate-400">{c.status}</span>
                )}
              </td>
            </tr>
          ))}
          {campaigns.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-center text-slate-400">No campaigns yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
