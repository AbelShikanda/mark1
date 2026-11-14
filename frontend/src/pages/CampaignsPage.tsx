import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';

type Campaign = {
  id: number;
  name: string;
  campaign_type: string;
  product_id: number | null;
  group_id: number | null;
  batch_ids?: number[] | null;
  client_id: number | null;
  client_ids?: number[] | null;
  my_group_link: string | null;
  scheduled_time: string | null;
  status: string;
  posts_sent: number;
  rePost: boolean;
  repeatPost: boolean;
  frequency: string | null;
  repeat_day: number | null;
  repeat_time: string | null;
  target_scope: string;
  auto_product: boolean;
  batch_size: number;
  duration_minutes: number;
  next_run_at: string | null;
  last_run_at: string | null;
};

type Product = { id: number; name: string; status: string; category: string | null };
type Group = { id: number; name: string; is_my_group: boolean; link: string | null; is_active: boolean };
type Client = { id: number; name: string };
type LiveRun = {
  id: number;
  campaign_id: number;
  campaign_name: string | null;
  status: string;
  phase: string;
  current_target: { name: string; attempts: number } | null;
  counts: {
    total: number;
    processed: number;
    sent: number;
    failed: number;
    skipped: number;
    remaining: number;
  };
};
type GroupBatch = {
  id: number;
  name: string;
  description: string | null;
  group_ids: number[];
  group_count: number;
  campaign_count: number;
};

const TYPE_LABELS: Record<string, string> = {
  product_group: 'Product → groups',
  product_client: 'Product → clients',
  myGroupLink: 'My group link → groups',
};

const STATUS_LABELS: Record<string, string> = {
  isScheduledFor: 'Scheduled',
  isRunning: 'Running',
  isBusy: 'Busy',
  isPosted: 'Done',
};

const STATUS_STYLES: Record<string, string> = {
  isRunning: 'bg-blue-100 text-blue-700',
  isBusy: 'bg-yellow-100 text-yellow-700',
  isPosted: 'bg-green-100 text-green-700',
  isScheduledFor: 'bg-slate-100 text-slate-600',
};

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function repeatSummary(c: Campaign): string {
  if (!c.repeatPost) return 'Once';
  const time = c.repeat_time || (c.scheduled_time ? c.scheduled_time.slice(11, 16) : '09:00');
  if (c.frequency === 'weekly') return `Weekly on ${WEEKDAYS[c.repeat_day ?? 0] ?? 'Monday'} at ${time}`;
  if (c.frequency === 'monthly') return `Monthly on day ${c.repeat_day ?? 1} at ${time}`;
  return `Daily at ${time}`;
}

const EMPTY = {
  name: '',
  type: 'product_group' as 'product_group' | 'product_client' | 'myGroupLink',
  productId: null as number | null,
  autoProduct: false,
  groupId: null as number | null,
  scope: 'single' as 'single' | 'batch' | 'all',
  batchSize: '0',
  scheduledTime: '',
  duration: '60',
  rePost: false,
  repeatPost: false,
  frequency: 'daily',
  repeatDay: '1',
  repeatTime: '',
};

export default function CampaignsPage({ onOpenLive }: { onOpenLive?: (campaignId?: number) => void }) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [liveRun, setLiveRun] = useState<LiveRun | null>(null);
  const [liveBusy, setLiveBusy] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [batches, setBatches] = useState<GroupBatch[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState(EMPTY.name);
  const [type, setType] = useState(EMPTY.type);
  const [selProd, setSelProd] = useState<number | null>(EMPTY.productId);
  const [autoProduct, setAutoProduct] = useState(EMPTY.autoProduct);
  const [selGrp, setSelGrp] = useState<number | null>(EMPTY.groupId);
  const [batchIds, setBatchIds] = useState<number[]>([]);
  const [clientIds, setClientIds] = useState<number[]>([]);
  const [scope, setScope] = useState<'single' | 'batch' | 'all'>(EMPTY.scope);
  const [batchSize, setBatchSize] = useState(EMPTY.batchSize);
  const [scheduledTime, setScheduledTime] = useState(EMPTY.scheduledTime);
  const [duration, setDuration] = useState(EMPTY.duration);
  const [rePost, setRePost] = useState(EMPTY.rePost);
  const [repeatPost, setRepeatPost] = useState(EMPTY.repeatPost);
  const [frequency, setFrequency] = useState(EMPTY.frequency);
  const [repeatDay, setRepeatDay] = useState(EMPTY.repeatDay);
  const [repeatTime, setRepeatTime] = useState(EMPTY.repeatTime);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    try {
      const [c, p, g, b, cl] = await Promise.all([
        api.get<Campaign[]>('/campaigns'),
        api.get<Product[]>('/products'),
        api.get<Group[]>('/groups'),
        api.get<GroupBatch[]>('/group-batches'),
        api.get<Client[]>('/clients'),
      ]);
      setCampaigns(Array.isArray(c.data) ? c.data : []);
      setProducts(Array.isArray(p.data) ? p.data : []);
      setGroups(Array.isArray(g.data) ? g.data : []);
      setBatches(Array.isArray(b.data) ? b.data : []);
      setClients(Array.isArray(cl.data) ? cl.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const res = await api.get<{ active: boolean; run: LiveRun | null }>('/live/active');
        if (!stopped) setLiveRun(res.data.active ? res.data.run : null);
      } catch {
        if (!stopped) setLiveRun(null);
      }
    };
    tick();
    const timer = window.setInterval(tick, 5000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

  const skipLiveTarget = async () => {
    if (!liveRun) return;
    const label = liveRun.current_target?.name ?? 'the current target';
    if (!window.confirm(`Skip “${label}”? It will not be counted as sent or missed.`)) return;
    setError(null);
    setNotice(null);
    setLiveBusy(true);
    try {
      const res = await api.post<{ message?: string }>(`/campaigns/${liveRun.campaign_id}/skip-current`);
      setNotice(res.data?.message ?? 'Skip requested; the runner will move to the next target.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLiveBusy(false);
    }
  };

  const resetForm = () => {
    setName(EMPTY.name);
    setType(EMPTY.type);
    setSelProd(EMPTY.productId);
    setAutoProduct(EMPTY.autoProduct);
    setSelGrp(EMPTY.groupId);
    setBatchIds([]);
    setClientIds([]);
    setScope(EMPTY.scope);
    setBatchSize(EMPTY.batchSize);
    setScheduledTime(EMPTY.scheduledTime);
    setDuration(EMPTY.duration);
    setRePost(EMPTY.rePost);
    setRepeatPost(EMPTY.repeatPost);
    setFrequency(EMPTY.frequency);
    setRepeatDay(EMPTY.repeatDay);
    setRepeatTime(EMPTY.repeatTime);
    setEditingId(null);
  };

  const startEdit = (c: Campaign) => {
    setEditingId(c.id);
    setName(c.name);
    setType(c.campaign_type as typeof type);
    setSelProd(c.product_id);
    setAutoProduct(Boolean(c.auto_product));
    setSelGrp(c.group_id);
    setBatchIds(Array.isArray(c.batch_ids) ? c.batch_ids : []);
    const ids = c.client_ids && c.client_ids.length
      ? c.client_ids
      : c.client_id
        ? [c.client_id]
        : [];
    setClientIds(ids);
    setScope((c.target_scope as 'single' | 'batch' | 'all') || 'single');
    setBatchSize(String(c.batch_size ?? 0));
    setScheduledTime((c.scheduled_time ?? '').replace(' ', 'T').slice(0, 16));
    setDuration(String(c.duration_minutes ?? 60));
    setRePost(Boolean(c.rePost));
    setRepeatPost(Boolean(c.repeatPost));
    setFrequency(c.frequency || 'daily');
    setRepeatDay(String(c.repeat_day ?? 1));
    setRepeatTime(c.repeat_time ?? '');
    setError(null);
    setNotice(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (type === 'product_group' && scope === 'single' && !selGrp) {
      setError('Select a group, or choose “All groups”.');
      return;
    }
    if (type === 'product_group' && scope === 'batch' && batchIds.length === 0) {
      setError('Select at least one group batch.');
      return;
    }
    if (type === 'product_client' && scope === 'single' && clientIds.length === 0) {
      setError('Select at least one client, or choose “All clients”.');
      return;
    }
    if (type !== 'myGroupLink' && !autoProduct && !selProd) {
      setError('Select a product, or choose “Auto by category”.');
      return;
    }
    if (repeatPost && !repeatTime && !scheduledTime) {
      setError('Repeat campaigns need a run time (or a start time).');
      return;
    }
    setSaving(true);
    const payload = {
      name,
      campaign_type: type,
      product_id: type === 'myGroupLink' || autoProduct ? null : selProd,
      group_id: type === 'product_group' && scope === 'single' ? selGrp : null,
      batch_ids: type === 'product_group' && scope === 'batch' ? batchIds : [],
      client_id: type === 'product_client' && scope === 'single' && clientIds.length === 1 ? clientIds[0] : null,
      client_ids: type === 'product_client' ? clientIds : [],
      my_group_link: null,
      scheduled_time: scheduledTime || null,
      rePost,
      repeatPost,
      frequency: repeatPost ? frequency : null,
      repeat_day: repeatPost ? parseInt(repeatDay, 10) || 1 : null,
      repeat_time: repeatPost ? repeatTime || (scheduledTime ? scheduledTime.slice(11, 16) : null) : null,
      target_scope: type === 'myGroupLink' ? 'all' : scope,
      auto_product: type === 'myGroupLink' ? false : autoProduct,
      batch_size: parseInt(batchSize, 10) || 0,
      duration_minutes: parseInt(duration, 10) || 60,
    };
    try {
      if (editingId) {
        await api.patch(`/campaigns/${editingId}`, payload);
        setNotice('Campaign updated; its schedule was recalculated.');
      } else {
        await api.post('/campaigns', payload);
        setNotice('Campaign created; its schedule was generated automatically.');
      }
      resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const run = async (id: number) => {
    setError(null);
    setNotice(null);
    setBusyId(id);
    try {
      const res = await api.post<{ status: string; message?: string }>(`/campaigns/${id}/start`);
      if (res.data?.status === 'isBusy') {
        setNotice(res.data.message || 'Another campaign is running; this one was moved to the next free slot.');
      }
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const stop = async (id: number) => {
    setError(null);
    setBusyId(id);
    try {
      await api.post(`/campaigns/${id}/stop`);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const cancel = async (id: number) => {
    if (!window.confirm('Cancel this campaign? Its schedule will be removed.')) return;
    setError(null);
    setBusyId(id);
    try {
      await api.post(`/campaigns/${id}/cancel`);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (c: Campaign) => {
    if (!window.confirm(`Delete campaign “${c.name}”? This cannot be undone.`)) return;
    setError(null);
    setBusyId(c.id);
    try {
      await api.delete(`/campaigns/${c.id}`);
      if (editingId === c.id) resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const myGroupsWithLinks = groups.filter((g) => g.is_my_group && g.link && g.link.trim());

  const changeType = (value: typeof type) => {
    setType(value);
    // "batch" only exists for product_group scopes; other kinds fall back to
    // their existing single/all choices.
    if (value !== 'product_group' && scope === 'batch') setScope('single');
  };

  const toggleClient = (id: number) => {
    setClientIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleBatch = (id: number) => {
    setBatchIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const selectedBatchGroupCount = new Set(
    batches
      .filter((b) => batchIds.includes(b.id))
      .flatMap((b) => b.group_ids ?? []),
  ).size;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Campaigns</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="flex items-start justify-between rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-blue-600 hover:text-blue-900">Dismiss</button>
        </div>
      )}

      <div className="bg-white p-4 rounded-lg border shadow-sm">
        <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input className="border rounded p-2" placeholder="Campaign name" value={name} onChange={(e) => setName(e.target.value)} />
          <select className="border rounded p-2" value={type} onChange={(e) => changeType(e.target.value as typeof type)}>
            <option value="product_group">Product → groups</option>
            <option value="product_client">Product → clients</option>
            <option value="myGroupLink">My group link → groups</option>
          </select>
          {type === 'myGroupLink' ? (
            <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
              Uses only “My groups” that have a link ({myGroupsWithLinks.length} ready). Core groups are skipped as targets.
            </div>
          ) : (
            <div className="flex items-center gap-3 rounded border border-slate-200 px-3 py-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="radio" checked={!autoProduct} onChange={() => setAutoProduct(false)} /> Fixed product
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" checked={autoProduct} onChange={() => setAutoProduct(true)} /> Auto by category
              </label>
            </div>
          )}

          {type !== 'myGroupLink' && !autoProduct && (
            <select className="border rounded p-2" value={selProd ?? ''} onChange={(e) => setSelProd(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Select product</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.status === 'isPosted' ? ' (posted - needs Re-post)' : ''}
                </option>
              ))}
            </select>
          )}

          {type === 'product_group' && (
            <>
              <select className="border rounded p-2" value={scope} onChange={(e) => setScope(e.target.value as 'single' | 'batch' | 'all')}>
                <option value="single">Single group</option>
                <option value="batch">Group batch(es)</option>
                <option value="all">All groups (batched, no repeats)</option>
              </select>
              {scope === 'single' ? (
                <select className="border rounded p-2" value={selGrp ?? ''} onChange={(e) => setSelGrp(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">Select group</option>
                  {groups.filter((g) => g.is_active !== false).map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              ) : scope === 'batch' ? (
                <div className="md:col-span-2 rounded border border-slate-200 p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                    <span>Select one or more batches ({batchIds.length} selected)</span>
                    <span className="font-medium text-slate-700">{selectedBatchGroupCount} unique group(s)</span>
                  </div>
                  {batches.length === 0 ? (
                    <div className="text-xs text-slate-400">Create group batches on the Groups page.</div>
                  ) : (
                    <div className="max-h-40 overflow-y-auto rounded border border-slate-100 p-1">
                      {batches.map((batch) => (
                        <label key={batch.id} className="flex items-center justify-between gap-2 rounded px-1 py-0.5 text-sm hover:bg-slate-50">
                          <span className="flex items-center gap-2">
                            <input type="checkbox" checked={batchIds.includes(batch.id)} onChange={() => toggleBatch(batch.id)} />
                            <span>{batch.name}</span>
                          </span>
                          <span className="text-xs text-slate-500">{batch.group_count} group(s)</span>
                        </label>
                      ))}
                    </div>
                  )}
                  <label className="block text-xs text-slate-500">
                    Groups per batch (0 = all at once)
                    <input className="mt-1 w-full border rounded p-2 text-sm" type="number" min="0" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} />
                  </label>
                </div>
              ) : (
                <input className="border rounded p-2" type="number" min="0" placeholder="Groups per batch (0 = all at once)" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} />
              )}
            </>
          )}

          {type === 'product_client' && (
            <>
              <select className="border rounded p-2" value={scope} onChange={(e) => setScope(e.target.value as 'single' | 'all')}>
                <option value="single">Selected clients</option>
                <option value="all">All clients (batched)</option>
              </select>
              {scope === 'single' ? (
                <div className="md:col-span-2 rounded border border-slate-200 p-2">
                  <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
                    <span>Choose one or more clients ({clientIds.length} selected)</span>
                    <div className="flex gap-2">
                      <button type="button" className="text-indigo-600 hover:underline" onClick={() => setClientIds(clients.map((c) => c.id))}>All</button>
                      <button type="button" className="text-slate-500 hover:underline" onClick={() => setClientIds([])}>Clear</button>
                    </div>
                  </div>
                  <div className="max-h-40 overflow-y-auto">
                    {clients.length === 0 && <div className="text-xs text-slate-400">No clients yet.</div>}
                    {clients.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 py-0.5 text-sm">
                        <input type="checkbox" checked={clientIds.includes(c.id)} onChange={() => toggleClient(c.id)} />
                        {c.name}
                      </label>
                    ))}
                  </div>
                  {clientIds.length > 1 && (
                    <label className="mt-2 block text-xs text-slate-500">
                      Clients per batch (0 = all at once)
                      <input className="mt-1 w-full border rounded p-2 text-sm" type="number" min="0" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} />
                    </label>
                  )}
                </div>
              ) : (
                <input className="border rounded p-2" type="number" min="0" placeholder="Clients per batch (0 = all at once)" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} />
              )}
            </>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={rePost} onChange={(e) => setRePost(e.target.checked)} /> Re-post even if already posted
          </label>

          <label className="text-xs text-slate-500 md:col-span-3">
            Start time (optional - leave empty for manual runs only)
            <input className="mt-1 w-full border rounded p-2 text-sm" type="datetime-local" value={scheduledTime} onChange={(e) => setScheduledTime(e.target.value)} />
          </label>
          <label className="text-xs text-slate-500">
            Run window (minutes)
            <input className="mt-1 w-full border rounded p-2 text-sm" type="number" min="5" value={duration} onChange={(e) => setDuration(e.target.value)} />
          </label>

          <div className="md:col-span-3 rounded border border-slate-200 p-3">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={repeatPost} onChange={(e) => setRepeatPost(e.target.checked)} /> Repeat this campaign
            </label>
            {repeatPost && (
              <div className="mt-2 grid grid-cols-1 md:grid-cols-4 gap-2">
                <select className="border rounded p-2 text-sm" value={frequency} onChange={(e) => setFrequency(e.target.value)}>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
                {frequency === 'weekly' && (
                  <select className="border rounded p-2 text-sm" value={repeatDay} onChange={(e) => setRepeatDay(e.target.value)}>
                    {WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}
                  </select>
                )}
                {frequency === 'monthly' && (
                  <input className="border rounded p-2 text-sm" type="number" min="1" max="31" placeholder="Day of month" value={repeatDay} onChange={(e) => setRepeatDay(e.target.value)} />
                )}
                <label className="text-xs text-slate-500">
                  At
                  <input className="mt-1 w-full border rounded p-2 text-sm" type="time" value={repeatTime} onChange={(e) => setRepeatTime(e.target.value)} />
                </label>
              </div>
            )}
          </div>

          <div className="md:col-span-3 flex gap-2">
            <button className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50" disabled={saving || !name}>
              {saving ? 'Saving…' : editingId ? 'Save changes' : 'Create campaign'}
            </button>
            {editingId && (
              <button type="button" onClick={resetForm} className="border border-slate-300 px-4 py-2 rounded text-slate-600 hover:bg-slate-50">
                Cancel edit
              </button>
            )}
          </div>
        </form>
      </div>

      {liveRun && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1.5 font-semibold">
              <span className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-indigo-500" />
              Live
            </span>
            <span>{liveRun.campaign_name ?? `Campaign ${liveRun.campaign_id}`}</span>
            <span className="rounded bg-white/70 px-2 py-0.5 text-xs text-indigo-700">{liveRun.status}</span>
            <span className="text-xs text-indigo-800">
              {liveRun.current_target ? `Now: ${liveRun.current_target.name}` : 'Waiting for the next target…'}
            </span>
            <span className="text-xs text-indigo-700">
              {liveRun.counts.processed}/{liveRun.counts.total} processed · {liveRun.counts.sent} sent · {liveRun.counts.failed} missed · {liveRun.counts.skipped} skipped · {liveRun.counts.remaining} remaining
            </span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onOpenLive?.(liveRun.campaign_id)}
              className="rounded border border-indigo-300 bg-white px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
            >
              Open live view
            </button>
            <button
              type="button"
              onClick={skipLiveTarget}
              disabled={liveBusy || !liveRun.current_target}
              className="rounded border border-amber-300 bg-white px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 disabled:opacity-40"
            >
              {liveBusy ? 'Skipping…' : 'Skip current'}
            </button>
          </div>
        </div>
      )}

      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Campaign</th>
            <th className="p-3 border-b">Target</th>
            <th className="p-3 border-b">Schedule</th>
            <th className="p-3 border-b">Status</th>
            <th className="p-3 border-b">Sent</th>
            <th className="p-3 border-b">Actions</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => {
            const product = products.find((p) => p.id === c.product_id);
            const group = groups.find((g) => g.id === c.group_id);
            const campaignBatches = batches.filter((b) => (c.batch_ids ?? []).includes(b.id));
            const campaignBatchGroupCount = new Set(campaignBatches.flatMap((b) => b.group_ids ?? [])).size;
            return (
              <tr key={c.id} className={`border-b hover:bg-slate-50 ${editingId === c.id ? 'bg-indigo-50/50' : ''}`}>
                <td className="p-3">
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-slate-500">{TYPE_LABELS[c.campaign_type] ?? c.campaign_type}</div>
                  <div className="text-xs text-slate-500">
                    {c.campaign_type === 'myGroupLink'
                      ? 'My groups with links'
                      : c.auto_product
                        ? 'Auto product (equitable by category)'
                        : `Product: ${product?.name ?? '—'}`}
                  </div>
                </td>
                <td className="p-3 text-xs text-slate-600">
                  {c.campaign_type === 'product_group' && (
                    c.target_scope === 'batch'
                      ? `${campaignBatches.map((b) => b.name).join(', ') || `${campaignBatches.length} batch(es)`} — ${campaignBatchGroupCount} groups from ${campaignBatches.length} batches${c.batch_size ? ` (${c.batch_size}/run)` : ''}`
                      : c.target_scope === 'all'
                        ? `All groups${c.batch_size ? ` (${c.batch_size}/run)` : ''}`
                        : group?.name ?? '—'
                  )}
                  {c.campaign_type === 'product_client' && (c.target_scope === 'all'
                    ? `All clients${c.batch_size ? ` (${c.batch_size}/run)` : ''}`
                    : (c.client_ids && c.client_ids.length
                        ? c.client_ids.map((id) => clients.find((cl) => cl.id === id)?.name ?? `#${id}`).join(', ')
                        : '—'))}
                  {c.campaign_type === 'myGroupLink' && 'Non-core groups'}
                </td>
                <td className="p-3 text-xs">
                  <div>{c.next_run_at ? `Next: ${c.next_run_at}` : 'Manual only'}</div>
                  <div className="text-slate-500">{repeatSummary(c)}</div>
                </td>
                <td className="p-3">
                  <span className={`px-2 py-1 rounded text-xs ${STATUS_STYLES[c.status] ?? 'bg-slate-100 text-slate-600'}`}>
                    {STATUS_LABELS[c.status] ?? c.status}
                  </span>
                </td>
                <td className="p-3">{c.posts_sent}</td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-2">
                    <button onClick={() => startEdit(c)} className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50">
                      Edit
                    </button>
                    <button
                      onClick={() => onOpenLive?.(c.id)}
                      className="rounded border border-sky-300 px-2 py-1 text-xs text-sky-700 hover:bg-sky-50"
                    >
                      Live
                    </button>
                    {c.status === 'isRunning' ? (
                      <button
                        onClick={() => stop(c.id)}
                        disabled={busyId === c.id}
                        className="rounded border border-orange-300 px-2 py-1 text-xs text-orange-700 hover:bg-orange-50 disabled:opacity-40"
                      >
                        {busyId === c.id ? 'Stopping…' : 'Stop'}
                      </button>
                    ) : (
                      <>
                        <button
                          onClick={() => run(c.id)}
                          disabled={busyId === c.id}
                          className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
                        >
                          {busyId === c.id ? 'Starting…' : c.status === 'isPosted' ? 'Run again' : 'Run now'}
                        </button>
                        <button
                          onClick={() => cancel(c.id)}
                          disabled={busyId === c.id}
                          className="rounded border border-amber-300 px-2 py-1 text-xs text-amber-700 hover:bg-amber-50 disabled:opacity-40"
                        >
                          Cancel
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => remove(c)}
                      disabled={busyId === c.id}
                      className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
          {campaigns.length === 0 && (
            <tr><td colSpan={6} className="p-4 text-center text-slate-400">No campaigns yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
