import { useEffect, useState } from 'react';
import { api } from '../api';

type Product = {
  id: number;
  name: string;
  description: string | null;
  media_url: string | null;
  link: string | null;
  source: string;
  status: string;
  posted_at: string | null;
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [link, setLink] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get<Product[]>('/products').then((r) => setProducts(r.data));
  }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const created = await api.post<Product>('/products', { name, description: desc, link, source: 'manual' });
    setProducts([created.data, ...products]);
    setName(''); setDesc(''); setLink('');
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Products</h1>
      <form onSubmit={add} className="grid grid-cols-1 md:grid-cols-4 gap-3 max-w-2xl">
        <input
          className="border rounded p-2"
          placeholder="Product name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="border rounded p-2"
          placeholder="Link"
          value={link}
          onChange={(e) => setLink(e.target.value)}
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
            <th className="p-3 border-b">Source</th>
            <th className="p-3 border-b">Status</th>
            <th className="p-3 border-b">Actions</th>
          </tr>
        </thead>
        <tbody>
          {products.map((p) => (
            <tr key={p.id} className="border-b hover:bg-slate-50">
              <td className="p-3">{p.name}</td>
              <td className="p-3 text-xs text-slate-500">{p.source}</td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded text-xs ${p.status === 'posted' ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-600'}`}>
                  {p.status}
                </span>
              </td>
              <td className="p-3">
                <button
                  className="text-red-600 hover:underline text-xs"
                  onClick={() => {
                    api.patch(`/products/${p.id}/status`, { status: 'posted' }).then(() =>
                      setProducts(products.map((x) => (x.id === p.id ? { ...x, status: 'posted' } : x)))
                    );
                  }}
                >
                  Mark posted
                </button>
              </td>
            </tr>
          ))}
          {products.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-center text-slate-400">No products yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
