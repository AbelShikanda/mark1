import { useEffect, useState } from 'react';
import { API_BASE, api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import { isValidMediaUrl, isValidUrl, normalizeMediaUrl, normalizeUrl } from '../validation';

type Product = {
  id: number;
  name: string;
  description: string | null;
  media_url: string | null;
  link: string | null;
  category: string | null;
  status: string;
  posted_at: string | null;
  last_posted_at: string | null;
};

const STATUS_LABELS: Record<string, string> = {
  isNotPosted: 'Not posted',
  isPending: 'Pending',
  isPosted: 'Posted',
};

const STATUS_STYLES: Record<string, string> = {
  isPosted: 'bg-green-100 text-green-700',
  isPending: 'bg-blue-100 text-blue-700',
  isNotPosted: 'bg-slate-100 text-slate-600',
};

const EMPTY = {
  name: '',
  description: '',
  mediaUrl: '',
  link: '',
  category: '',
};

type SeedSummary = {
  inserted: number;
  updated: number;
  skipped: number;
  total: number;
  warnings: string[];
};

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mediaUrl, setMediaUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [link, setLink] = useState('');
  const [category, setCategory] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedSummary, setSeedSummary] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await api.get<Product[]>('/products');
      setProducts(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const resetForm = () => {
    setName(EMPTY.name);
    setDescription(EMPTY.description);
    setMediaUrl(EMPTY.mediaUrl);
    setFile(null);
    setLink(EMPTY.link);
    setCategory(EMPTY.category);
    setEditingId(null);
  };

  const startEdit = (p: Product) => {
    setEditingId(p.id);
    setName(p.name);
    setDescription(p.description ?? '');
    setMediaUrl(p.media_url ?? '');
    setLink(p.link ?? '');
    setCategory(p.category ?? '');
    setFile(null);
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const uploadImage = async (selected: File): Promise<string> => {
    const form = new FormData();
    form.append('file', selected);
    const res = await api.post<{ media_url: string }>('/upload', form);
    if (!res.data?.media_url) throw new Error('Upload failed: the server did not return a media URL.');
    return res.data.media_url;
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!isValidUrl(link)) {
      setError('Enter a valid link, for example https://example.com');
      return;
    }
    if (!isValidMediaUrl(mediaUrl)) {
      setError('Enter a valid image URL, for example https://example.com/image.jpg');
      return;
    }

    setSaving(true);
    try {
      let media = normalizeMediaUrl(mediaUrl) || null;
      if (file) {
        setUploading(true);
        media = await uploadImage(file);
        setUploading(false);
      }
      const payload = {
        name: name.trim(),
        description: description || null,
        media_url: media,
        link: normalizeUrl(link) || null,
        category: category || null,
        status: editingId
          ? products.find((p) => p.id === editingId)?.status ?? 'isNotPosted'
          : 'isNotPosted',
      };
      if (editingId) {
        await api.patch(`/products/${editingId}`, payload);
      } else {
        await api.post('/products', payload);
      }
      resetForm();
      await load();
    } catch (err) {
      setUploading(false);
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (id: number, status: string) => {
    setError(null);
    setBusyId(id);
    try {
      await api.patch(`/products/${id}/status`, { status });
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (p: Product) => {
    if (!window.confirm(`Delete product “${p.name}”? This cannot be undone.`)) return;
    setError(null);
    setBusyId(p.id);
    try {
      await api.delete(`/products/${p.id}`);
      if (editingId === p.id) resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const resetAll = async () => {
    if (!window.confirm('Reset every product to “Not posted”?')) return;
    setError(null);
    try {
      await api.post('/products/reset-all');
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const seedProducts = async () => {
    if (
      !window.confirm(
        'Import products from backend/adopt/products? Existing products are not overwritten or deleted, and re-running only adds missing links.',
      )
    )
      return;
    setError(null);
    setSeedSummary(null);
    setSeeding(true);
    try {
      const res = await api.post<SeedSummary>('/admin/seed-products');
      const s = res.data;
      const warningText = s.warnings?.length
        ? ` ${s.warnings.length} warning${s.warnings.length === 1 ? '' : 's'} — see Logs.`
        : '';
      setSeedSummary(
        `Seed complete: ${s.inserted} inserted, ${s.updated} updated, ${s.skipped} skipped (${s.total} candidates).${warningText}`,
      );
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSeeding(false);
    }
  };

  const query = search.trim().toLowerCase();
  const visibleProducts = products.filter((p) => {
    const matchesSearch =
      !query ||
      p.name.toLowerCase().includes(query) ||
      (p.link ?? '').toLowerCase().includes(query) ||
      (p.category ?? '').toLowerCase().includes(query);
    const matchesStatus = statusFilter === 'all' || p.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Products</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {seedSummary && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          <span>{seedSummary}</span>
          <button
            type="button"
            onClick={() => setSeedSummary(null)}
            className="text-xs text-emerald-700 hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="bg-white p-4 rounded-lg border shadow-sm">
        <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input className="border rounded p-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="border rounded p-2" placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input className="border rounded p-2" inputMode="url" placeholder="Link (e.g. example.com)" value={link} onChange={(e) => setLink(e.target.value)} />
          <input className="border rounded p-2 md:col-span-3" placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          <input className="border rounded p-2 md:col-span-2" inputMode="url" placeholder="Image URL (e.g. example.com/pic.jpg) or upload" value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} />
          <div className="flex items-center gap-2">
            <input type="file" accept="image/*" onChange={(e) => {
              if (e.target.files?.length) setFile(e.target.files[0]);
            }} />
            {file && <span className="text-xs text-slate-500">{file.name}</span>}
          </div>
          <div className="flex gap-2 md:col-span-3">
            <button
              className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
              disabled={saving || !name}
            >
              {uploading ? 'Uploading image…' : saving ? 'Saving…' : editingId ? 'Save changes' : 'Add product'}
            </button>
            {editingId && (
              <button type="button" onClick={resetForm} className="border border-slate-300 px-4 py-2 rounded text-slate-600 hover:bg-slate-50">
                Cancel edit
              </button>
            )}
            <button type="button" onClick={resetAll} className="ml-auto text-xs text-slate-600 hover:text-slate-900 hover:underline">
              Reset every product to “Not posted”
            </button>
            <button
              type="button"
              onClick={seedProducts}
              disabled={seeding}
              className="rounded border border-emerald-300 px-3 py-2 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
            >
              {seeding ? 'Seeding…' : 'Seed products'}
            </button>
          </div>
        </form>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-2 sm:flex-row">
          <input
            className="w-full rounded border p-2 text-sm sm:max-w-sm"
            placeholder="Search name, link or category"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className="rounded border p-2 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All statuses</option>
            <option value="isNotPosted">Not posted</option>
            <option value="isPending">Pending</option>
            <option value="isPosted">Posted</option>
          </select>
        </div>
        <div className="text-xs text-slate-500">
          Showing {visibleProducts.length} of {products.length} products
        </div>
      </div>

      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Product</th>
            <th className="p-3 border-b">Category</th>
            <th className="p-3 border-b">Status</th>
            <th className="p-3 border-b">Actions</th>
          </tr>
        </thead>
        <tbody>
          {visibleProducts.map((p) => (
            <tr key={p.id} className={`border-b hover:bg-slate-50 ${editingId === p.id ? 'bg-indigo-50/50' : ''}`}>
              <td className="p-3">
                <div className="flex items-start gap-3">
                  {p.media_url && (
                    <img
                      src={p.media_url.startsWith('http') || p.media_url.startsWith('data:') ? p.media_url : `${API_BASE}${p.media_url}`}
                      alt={p.name}
                      className="h-10 w-10 rounded object-cover border"
                      onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                    />
                  )}
                  <div>
                    <div className="font-medium">{p.name}</div>
                    {p.description && <div className="text-xs text-slate-500 line-clamp-2">{p.description}</div>}
                    {p.link && <div className="text-xs text-indigo-600 truncate max-w-xs">{p.link}</div>}
                  </div>
                </div>
              </td>
              <td className="p-3 text-slate-500 text-xs">{p.category ?? '-'}</td>
              <td className="p-3">
                <span className={`px-2 py-1 rounded text-xs ${STATUS_STYLES[p.status] ?? 'bg-slate-100 text-slate-600'}`}>
                  {STATUS_LABELS[p.status] ?? p.status}
                </span>
              </td>
              <td className="p-3">
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => startEdit(p)}
                    className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => setStatus(p.id, 'isNotPosted')}
                    disabled={busyId === p.id || p.status === 'isNotPosted'}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40"
                  >
                    Not posted
                  </button>
                  <button
                    onClick={() => setStatus(p.id, 'isPending')}
                    disabled={busyId === p.id || p.status === 'isPending'}
                    className="rounded border border-blue-300 px-2 py-1 text-xs text-blue-700 hover:bg-blue-50 disabled:opacity-40"
                  >
                    Pending
                  </button>
                  <button
                    onClick={() => setStatus(p.id, 'isPosted')}
                    disabled={busyId === p.id || p.status === 'isPosted'}
                    className="rounded border border-green-300 px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:opacity-40"
                  >
                    Posted
                  </button>
                  <button
                    onClick={() => remove(p)}
                    disabled={busyId === p.id}
                    className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                  >
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {visibleProducts.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-center text-slate-400">
              {products.length === 0 ? 'No products yet.' : 'No products match the current filters.'}
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
