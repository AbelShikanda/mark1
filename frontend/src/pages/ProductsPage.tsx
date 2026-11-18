import { useEffect, useMemo, useState } from 'react';
import { API_BASE, api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { isValidMediaUrl, isValidUrl, normalizeMediaUrl, normalizeUrl } from '../validation';
import { BTN_PRIMARY, CARD_PAD, INPUT, MUTED, NOTICE_SUCCESS } from '../ui';

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
  isPosted: 'bg-green-100 text-green-700 dark:bg-emerald-950/60 dark:text-emerald-300',
  isPending: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300',
  isNotPosted: 'bg-slate-100 text-slate-600 dark:bg-[#111] dark:text-[#d4d4d4]',
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

const STATUS_OPTIONS = [
  { value: 'isNotPosted', label: 'Not posted' },
  { value: 'isPending', label: 'Pending' },
  { value: 'isPosted', label: 'Posted' },
];

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

  const categories = useMemo(
    () =>
      Array.from(new Set(products.map((item) => item.category).filter(Boolean) as string[]))
        .sort((a, b) => a.localeCompare(b))
        .map((value) => ({ value, label: value })),
    [products],
  );

  const table = useTableFilters<Product>(
    products,
    (product) =>
      [product.name, product.link, product.category, product.description].filter(Boolean).join(' '),
    [
      { key: 'product', label: 'Product', getValue: (product) => `${product.name} ${product.description ?? ''}` },
      { key: 'category', label: 'Category', type: 'select', options: categories, getValue: (product) => product.category ?? '' },
      { key: 'status', label: 'Status', type: 'select', options: STATUS_OPTIONS, getValue: (product) => product.status },
    ],
    { category: '', status: '' },
  );

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

  const columns: DataTableColumn<Product>[] = [
    {
      key: 'product',
      header: 'Product',
      filter: { type: 'text', placeholder: 'Filter product' },
      cell: (p) => (
        <div className="flex items-start gap-3">
          {p.media_url && (
            <img
              src={p.media_url.startsWith('http') || p.media_url.startsWith('data:') ? p.media_url : `${API_BASE}${p.media_url}`}
              alt={p.name}
              className="h-10 w-10 rounded border border-slate-200 object-cover dark:border-[#222]"
              onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
            />
          )}
          <div>
            <div className="font-medium">{p.name}</div>
            {p.description && <div className="line-clamp-2 text-xs text-slate-500 dark:text-[#a3a3a3]">{p.description}</div>}
            {p.link && <div className="max-w-xs truncate text-xs text-indigo-600 dark:text-indigo-400">{p.link}</div>}
          </div>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      filter: { type: 'select', options: categories, placeholder: 'All categories' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (p) => p.category ?? '-',
    },
    {
      key: 'status',
      header: 'Status',
      filter: { type: 'select', options: STATUS_OPTIONS, placeholder: 'All statuses' },
      cell: (p) => (
        <span className={`rounded px-2 py-1 text-xs ${STATUS_STYLES[p.status] ?? 'bg-slate-100 text-slate-600 dark:bg-[#111] dark:text-[#d4d4d4]'}`}>
          {STATUS_LABELS[p.status] ?? p.status}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (p) => (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => startEdit(p)}
            className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950/50"
          >
            Edit
          </button>
          <button
            onClick={() => setStatus(p.id, 'isNotPosted')}
            disabled={busyId === p.id || p.status === 'isNotPosted'}
            className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40 dark:border-[#2a2a2a] dark:text-[#e5e5e5] dark:hover:bg-[#161616]"
          >
            Not posted
          </button>
          <button
            onClick={() => setStatus(p.id, 'isPending')}
            disabled={busyId === p.id || p.status === 'isPending'}
            className="rounded border border-blue-300 px-2 py-1 text-xs text-blue-700 hover:bg-blue-50 disabled:opacity-40 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-950/50"
          >
            Pending
          </button>
          <button
            onClick={() => setStatus(p.id, 'isPosted')}
            disabled={busyId === p.id || p.status === 'isPosted'}
            className="rounded border border-green-300 px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:opacity-40 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/50"
          >
            Posted
          </button>
          <button
            onClick={() => remove(p)}
            disabled={busyId === p.id}
            className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
          >
            Delete
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Products</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {seedSummary && (
        <div className={`flex items-start justify-between gap-3 ${NOTICE_SUCCESS}`}>
          <span>{seedSummary}</span>
          <button
            type="button"
            onClick={() => setSeedSummary(null)}
            className="text-xs text-emerald-700 hover:underline dark:text-emerald-300"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className={CARD_PAD}>
        <form onSubmit={save} className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <input className={INPUT} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={INPUT} placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input className={INPUT} inputMode="url" placeholder="Link (e.g. example.com)" value={link} onChange={(e) => setLink(e.target.value)} />
          <input className={`${INPUT} md:col-span-3`} placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
          <input className={`${INPUT} md:col-span-2`} inputMode="url" placeholder="Image URL (e.g. example.com/pic.jpg) or upload" value={mediaUrl} onChange={(e) => setMediaUrl(e.target.value)} />
          <div className="flex items-center gap-2">
            <input type="file" accept="image/*" onChange={(e) => {
              if (e.target.files?.length) setFile(e.target.files[0]);
            }} />
            {file && <span className={`text-xs ${MUTED}`}>{file.name}</span>}
          </div>
          <div className="flex flex-wrap gap-2 md:col-span-3">
            <button className={BTN_PRIMARY} disabled={saving || !name}>
              {uploading ? 'Uploading image…' : saving ? 'Saving…' : editingId ? 'Save changes' : 'Add product'}
            </button>
            {editingId && (
              <button type="button" onClick={resetForm} className="rounded border border-slate-300 px-4 py-2 text-slate-600 hover:bg-slate-50 dark:border-[#2a2a2a] dark:text-[#d4d4d4] dark:hover:bg-[#161616]">
                Cancel edit
              </button>
            )}
            <button type="button" onClick={resetAll} className="ml-auto text-xs text-slate-600 hover:text-slate-900 hover:underline dark:text-[#a3a3a3] dark:hover:text-slate-100">
              Reset every product to “Not posted”
            </button>
            <button
              type="button"
              onClick={seedProducts}
              disabled={seeding}
              className="rounded border border-emerald-300 px-3 py-2 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/50"
            >
              {seeding ? 'Seeding…' : 'Seed products'}
            </button>
          </div>
        </form>
      </div>

      <div className="space-y-2">
        <TableToolbar
          search={table.search}
          onSearch={table.setSearch}
          placeholder="Search name, link, category or description"
          count={table.count}
          total={table.total}
          onClear={table.clearFilters}
          isFiltered={table.isFiltered}
        />
      </div>

      <DataTable
        columns={columns}
        rows={table.filtered}
        rowKey={(p) => p.id}
        filters={table.values}
        onFilterChange={table.setFilter}
        emptyMessage={products.length === 0 ? 'No products yet.' : 'No products match the current filters.'}
        rowClassName={(p) => (editingId === p.id ? 'bg-indigo-50/50 dark:bg-indigo-950/30' : '')}
      />
    </div>
  );
}
