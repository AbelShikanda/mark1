import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import { isValidUrl, normalizeUrl } from '../validation';

type Group = {
  id: number;
  name: string;
  category: string | null;
  location: string | null;
  n: number;
  isPostedProductToday: number;
  link: string | null;
  is_my_group: boolean;
  is_core: boolean;
  failures: number;
  is_active: boolean;
  total_misses: number;
  is_silenced: boolean;
  silenced_at: string | null;
  silence_reason: string | null;
  last_missed_at: string | null;
  last_success_at: string | null;
};

type GroupBatch = {
  id: number;
  name: string;
  description: string | null;
  group_ids: number[];
  group_count: number;
  campaign_count: number;
  created_at: string | null;
  updated_at: string | null;
};

const EMPTY = {
  name: '',
  category: '',
  location: '',
  n: '1',
  link: '',
  isMyGroup: false,
  isCore: false,
};

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [name, setName] = useState('');
  const [category, setCategory] = useState('');
  const [location, setLocation] = useState('');
  const [n, setN] = useState('1');
  const [link, setLink] = useState('');
  const [isMyGroup, setIsMyGroup] = useState(false);
  const [isCore, setIsCore] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [filter, setFilter] = useState<'all' | 'mine' | 'core' | 'inactive'>('all');
  const [view, setView] = useState<'groups' | 'batches' | 'silenced'>('groups');
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [batches, setBatches] = useState<GroupBatch[]>([]);
  const [batchName, setBatchName] = useState('');
  const [batchDescription, setBatchDescription] = useState('');
  const [batchGroupIds, setBatchGroupIds] = useState<number[]>([]);
  const [batchSearch, setBatchSearch] = useState('');
  const [editingBatchId, setEditingBatchId] = useState<number | null>(null);
  const [batchSaving, setBatchSaving] = useState(false);
  const [batchBusyId, setBatchBusyId] = useState<number | null>(null);

  const load = async () => {
    try {
      const [groupRes, batchRes] = await Promise.all([
        api.get<Group[]>('/groups'),
        api.get<GroupBatch[]>('/group-batches'),
      ]);
      setGroups(Array.isArray(groupRes.data) ? groupRes.data : []);
      setBatches(Array.isArray(batchRes.data) ? batchRes.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const resetForm = () => {
    setName(EMPTY.name);
    setCategory(EMPTY.category);
    setLocation(EMPTY.location);
    setN(EMPTY.n);
    setLink(EMPTY.link);
    setIsMyGroup(EMPTY.isMyGroup);
    setIsCore(EMPTY.isCore);
    setEditingId(null);
  };

  const startEdit = (g: Group) => {
    setView('groups');
    setEditingId(g.id);
    setName(g.name);
    setCategory(g.category ?? '');
    setLocation(g.location ?? '');
    setN(String(g.n));
    setLink(g.link ?? '');
    setIsMyGroup(Boolean(g.is_my_group));
    setIsCore(Boolean(g.is_core));
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isValidUrl(link)) {
      setError('Enter a valid group link, for example https://chat.whatsapp.com/…');
      return;
    }
    setSaving(true);
    const payload = {
      name: name.trim(),
      category: category || null,
      location: location || null,
      n: parseInt(n, 10) || 1,
      link: normalizeUrl(link) || null,
      is_my_group: isMyGroup,
      is_core: isCore,
    };
    try {
      if (editingId) {
        await api.patch(`/groups/${editingId}`, payload);
      } else {
        await api.post('/groups', payload);
      }
      resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (group: Group) => {
    if (!window.confirm(`Delete group “${group.name}”? This cannot be undone.`)) return;
    setError(null);
    setBusyId(group.id);
    try {
      await api.delete(`/groups/${group.id}`);
      if (editingId === group.id) resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (group: Group) => {
    setError(null);
    setBusyId(group.id);
    try {
      await api.patch(`/groups/${group.id}/active`, { is_active: !group.is_active });
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const unsilence = async (group: Group) => {
    setError(null);
    setBusyId(group.id);
    try {
      await api.post(`/groups/${group.id}/unsilence`);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const resetBatchForm = () => {
    setBatchName('');
    setBatchDescription('');
    setBatchGroupIds([]);
    setBatchSearch('');
    setEditingBatchId(null);
  };

  const startEditBatch = (batch: GroupBatch) => {
    setView('batches');
    setEditingBatchId(batch.id);
    setBatchName(batch.name);
    setBatchDescription(batch.description ?? '');
    setBatchGroupIds(Array.isArray(batch.group_ids) ? batch.group_ids : []);
    setBatchSearch('');
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const toggleBatchGroup = (id: number) => {
    setBatchGroupIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const saveBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!batchName.trim()) {
      setError('Give the group batch a name.');
      return;
    }
    if (batchGroupIds.length === 0) {
      setError('Select at least one group for this batch.');
      return;
    }
    setBatchSaving(true);
    const payload = {
      name: batchName.trim(),
      description: batchDescription.trim() || null,
      group_ids: batchGroupIds,
    };
    try {
      if (editingBatchId) {
        await api.patch(`/group-batches/${editingBatchId}`, payload);
      } else {
        await api.post('/group-batches', payload);
      }
      resetBatchForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBatchSaving(false);
    }
  };

  const removeBatch = async (batch: GroupBatch) => {
    if (!window.confirm(`Delete group batch “${batch.name}”? This cannot be undone.`)) return;
    setError(null);
    setBatchBusyId(batch.id);
    try {
      await api.delete(`/group-batches/${batch.id}`);
      if (editingBatchId === batch.id) resetBatchForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBatchBusyId(null);
    }
  };

  const batchSearchTerm = batchSearch.trim().toLowerCase();
  const batchGroupOptions = groups.filter((g) => {
    if (!batchSearchTerm) return true;
    return [g.name, g.category, g.location].some((value) =>
      (value ?? '').toLowerCase().includes(batchSearchTerm),
    );
  });

  const selectAllBatchGroups = () => {
    setBatchGroupIds((prev) => Array.from(new Set([...prev, ...batchGroupOptions.map((g) => g.id)])));
  };

  const clearBatchGroups = () => setBatchGroupIds([]);

  const visible = groups.filter((g) => {
    if (filter === 'mine') return Boolean(g.is_my_group);
    if (filter === 'core') return Boolean(g.is_core);
    if (filter === 'inactive') return !g.is_active;
    return true;
  });
  const silencedGroups = groups.filter((g) => Boolean(g.is_silenced));

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Groups</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="sticky top-0 z-20 -mx-6 flex w-[calc(100%+3rem)] gap-1 border-b border-slate-200 bg-gray-50/95 px-6 py-2 backdrop-blur">
        <button
          type="button"
          onClick={() => setView('groups')}
          className={`rounded-t border-b-2 px-4 py-2 text-sm font-medium ${view === 'groups' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
        >
          Groups <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600">{groups.length}</span>
        </button>
        <button
          type="button"
          onClick={() => setView('silenced')}
          className={`rounded-t border-b-2 px-4 py-2 text-sm font-medium ${view === 'silenced' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
        >
          Silenced <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">{silencedGroups.length}</span>
        </button>
        <button
          type="button"
          onClick={() => setView('batches')}
          className={`rounded-t border-b-2 px-4 py-2 text-sm font-medium ${view === 'batches' ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-500 hover:text-slate-800'}`}
        >
          Group batches <span className="ml-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">{batches.length}</span>
        </button>
      </div>

      {view === 'groups' && (
        <>
      <div className="bg-white p-4 rounded-lg border shadow-sm">
        <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input className="border rounded p-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="border rounded p-2" placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input className="border rounded p-2" placeholder="Location / region (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
          <input className="border rounded p-2" type="number" min="1" placeholder="Posts per day (n)" value={n} onChange={(e) => setN(e.target.value)} />
          <input className="border rounded p-2 md:col-span-2" inputMode="url" placeholder="My group link (e.g. chat.whatsapp.com/…)" value={link} onChange={(e) => setLink(e.target.value)} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isMyGroup} onChange={(e) => setIsMyGroup(e.target.checked)} /> My group
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isCore} onChange={(e) => setIsCore(e.target.checked)} /> Core group
          </label>
          <div className="flex gap-2">
            <button className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50" disabled={saving || !name}>
              {saving ? 'Saving…' : editingId ? 'Save changes' : 'Add group'}
            </button>
            {editingId && (
              <button type="button" onClick={resetForm} className="border border-slate-300 px-4 py-2 rounded text-slate-600 hover:bg-slate-50">
                Cancel
              </button>
            )}
          </div>
        </form>
        <p className="mt-2 text-xs text-slate-500">
          Core groups are prioritised as link sources and excluded as link targets. Only “My groups” with a link are used by link campaigns.
        </p>
        <p className="mt-2 text-xs text-slate-500">
          The silence threshold and other automation parameters live on the Settings page.
        </p>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">Show:</span>
        <select className="border rounded p-2 text-sm" value={filter} onChange={(e) => setFilter(e.target.value as typeof filter)}>
          <option value="all">All groups</option>
          <option value="mine">My groups</option>
          <option value="core">Core groups</option>
          <option value="inactive">Disabled groups</option>
        </select>
        <span className="text-xs text-slate-400">{visible.length} shown</span>
      </div>

      <div className="max-h-[65vh] w-full overflow-auto rounded-lg border border-slate-200">
      <table className="w-full min-w-[760px] border-collapse">
        <thead className="sticky top-0 z-10">
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Name</th>
            <th className="p-3 border-b">Category</th>
            <th className="p-3 border-b">Location</th>
            <th className="p-3 border-b">Posted today / limit</th>
            <th className="p-3 border-b">Misses</th>
            <th className="p-3 border-b">Tags</th>
            <th className="p-3 border-b">Actions</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((g) => (
            <tr key={g.id} className={`border-b hover:bg-slate-50 ${editingId === g.id ? 'bg-indigo-50/50' : ''}`}>
              <td className="p-3">
                <div className="font-medium">{g.name}</div>
                {g.link && <div className="text-xs text-indigo-600 truncate max-w-xs">{g.link}</div>}
                {g.failures > 0 && <div className="text-xs text-orange-600">{g.failures} consecutive miss(es)</div>}
                {g.is_silenced && <div className="text-xs text-red-600">Silenced: {g.silence_reason ?? 'too many misses'}</div>}
              </td>
              <td className="p-3 text-slate-500 text-xs">{g.category ?? '-'}</td>
              <td className="p-3 text-slate-500 text-xs">{g.location ?? '-'}</td>
              <td className="p-3 text-xs">{g.isPostedProductToday} / {g.n}</td>
              <td className="p-3 text-xs">
                <div>{g.total_misses ?? 0} total</div>
                {g.last_missed_at && <div className="text-slate-400">last {g.last_missed_at}</div>}
              </td>
              <td className="p-3">
                <div className="flex flex-wrap gap-1">
                  {g.is_my_group && <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">Mine</span>}
                  {g.is_core && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Core</span>}
                  {!g.is_active && <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">Disabled</span>}
                  {g.is_silenced && <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">Silenced</span>}
                </div>
              </td>
              <td className="p-3">
                <div className="flex flex-wrap gap-2">
                  <button onClick={() => startEdit(g)} className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50">
                    Edit
                  </button>
                  {g.is_silenced && (
                    <button
                      onClick={() => unsilence(g)}
                      disabled={busyId === g.id}
                      className="rounded border border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
                    >
                      {busyId === g.id ? 'Clearing…' : 'Unsilence'}
                    </button>
                  )}
                  <button
                    onClick={() => toggleActive(g)}
                    disabled={busyId === g.id}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-40"
                  >
                    {g.is_active ? 'Disable' : 'Enable'}
                  </button>
                  <button
                    onClick={() => remove(g)}
                    disabled={busyId === g.id}
                    className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                  >
                    {busyId === g.id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {visible.length === 0 && (
            <tr><td colSpan={7} className="p-4 text-center text-slate-400">No groups match this filter.</td></tr>
          )}
        </tbody>
      </table>
      </div>
        </>
      )}

      {view === 'silenced' && (
        <div className="w-full space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div>
            <h2 className="text-xl font-bold">Silenced groups</h2>
            <p className="mt-1 text-xs text-slate-500">
              Groups are silenced after repeated consecutive misses and are skipped by campaigns until you clear them.
              Clearing a group resets its consecutive miss count so it becomes eligible again.
            </p>
          </div>

          <div className="max-h-[65vh] w-full overflow-auto rounded-lg border border-slate-200">
            <table className="w-full min-w-[760px] border-collapse">
              <thead className="sticky top-0 z-10">
                <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
                  <th className="p-3 border-b">Group</th>
                  <th className="p-3 border-b">Category</th>
                  <th className="p-3 border-b">Location</th>
                  <th className="p-3 border-b">Misses</th>
                  <th className="p-3 border-b">Silenced</th>
                  <th className="p-3 border-b">Last success</th>
                  <th className="p-3 border-b">Actions</th>
                </tr>
              </thead>
              <tbody>
                {silencedGroups.map((g) => (
                  <tr key={g.id} className="border-b hover:bg-slate-50">
                    <td className="p-3">
                      <div className="font-medium">{g.name}</div>
                      {g.link && <div className="text-xs text-indigo-600 truncate max-w-xs">{g.link}</div>}
                      <div className="text-xs text-red-600">{g.silence_reason ?? 'Too many consecutive misses'}</div>
                    </td>
                    <td className="p-3 text-slate-500 text-xs">{g.category ?? '-'}</td>
                    <td className="p-3 text-slate-500 text-xs">{g.location ?? '-'}</td>
                    <td className="p-3 text-xs">
                      <div>{g.total_misses ?? 0} total</div>
                      <div className="text-orange-600">{g.failures ?? 0} consecutive</div>
                    </td>
                    <td className="p-3 text-xs text-slate-500">{g.silenced_at ?? '-'}</td>
                    <td className="p-3 text-xs text-slate-500">{g.last_success_at ?? '-'}</td>
                    <td className="p-3">
                      <div className="flex flex-wrap gap-2">
                        <button onClick={() => startEdit(g)} className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50">
                          Edit
                        </button>
                        <button
                          onClick={() => unsilence(g)}
                          disabled={busyId === g.id}
                          className="rounded border border-emerald-300 px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50 disabled:opacity-40"
                        >
                          {busyId === g.id ? 'Clearing…' : 'Unsilence'}
                        </button>
                        <button
                          onClick={() => remove(g)}
                          disabled={busyId === g.id}
                          className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {silencedGroups.length === 0 && (
                  <tr><td colSpan={7} className="p-4 text-center text-slate-400">No groups are silenced.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {view === 'batches' && (
      <div className="w-full space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <h2 className="text-xl font-bold">Group batches</h2>
          <p className="mt-1 text-xs text-slate-500">
            Reusable, live-linked presets. A campaign that uses a batch always resolves its groups at run time, so
            editing the batch changes every campaign that references it on its next run.
          </p>
        </div>

        <form onSubmit={saveBatch} className="space-y-3 rounded border border-slate-200 p-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              className="border rounded p-2"
              placeholder="Batch name"
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
            />
            <input
              className="border rounded p-2"
              placeholder="Description (optional)"
              value={batchDescription}
              onChange={(e) => setBatchDescription(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <input
              className="min-w-[220px] flex-1 border rounded p-2 text-sm"
              placeholder="Search groups by name, category or location"
              value={batchSearch}
              onChange={(e) => setBatchSearch(e.target.value)}
            />
            <button type="button" className="text-indigo-600 hover:underline" onClick={selectAllBatchGroups}>
              Select all
            </button>
            <button type="button" className="text-slate-500 hover:underline" onClick={clearBatchGroups}>
              Clear
            </button>
            <span className="font-medium text-slate-700">{batchGroupIds.length} selected</span>
          </div>

          <div className="max-h-64 overflow-y-auto rounded border border-slate-200 p-2">
            {batchGroupOptions.length === 0 && (
              <div className="p-2 text-xs text-slate-400">No groups match this search.</div>
            )}
            {batchGroupOptions.map((g) => (
              <label key={g.id} className="flex items-center justify-between gap-2 rounded px-1 py-1 text-sm hover:bg-slate-50">
                <span className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={batchGroupIds.includes(g.id)}
                    onChange={() => toggleBatchGroup(g.id)}
                  />
                  <span>{g.name}</span>
                </span>
                <span className="flex flex-wrap justify-end gap-1">
                  {g.is_core && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Core</span>}
                  {g.is_active ? (
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700">Active</span>
                  ) : (
                    <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">Disabled</span>
                  )}
                </span>
              </label>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50"
              disabled={batchSaving || !batchName.trim() || batchGroupIds.length === 0}
            >
              {batchSaving ? 'Saving…' : editingBatchId ? 'Save batch changes' : 'Create batch'}
            </button>
            {editingBatchId && (
              <button
                type="button"
                onClick={resetBatchForm}
                className="border border-slate-300 px-4 py-2 rounded text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
            )}
          </div>
        </form>

        <div className="max-h-[55vh] w-full overflow-auto rounded-lg border border-slate-200">
        <table className="w-full min-w-[620px] border-collapse">
          <thead className="sticky top-0 z-10">
            <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
              <th className="p-3 border-b">Batch</th>
              <th className="p-3 border-b">Groups</th>
              <th className="p-3 border-b">Used by campaigns</th>
              <th className="p-3 border-b">Updated</th>
              <th className="p-3 border-b">Actions</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((batch) => (
              <tr key={batch.id} className={`border-b hover:bg-slate-50 ${editingBatchId === batch.id ? 'bg-indigo-50/50' : ''}`}>
                <td className="p-3">
                  <div className="font-medium">{batch.name}</div>
                  {batch.description && <div className="text-xs text-slate-500">{batch.description}</div>}
                </td>
                <td className="p-3 text-xs">{batch.group_count ?? batch.group_ids?.length ?? 0}</td>
                <td className="p-3 text-xs">{batch.campaign_count ?? 0}</td>
                <td className="p-3 text-xs text-slate-500">{batch.updated_at ?? batch.created_at ?? '—'}</td>
                <td className="p-3">
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => startEditBatch(batch)}
                      className="rounded border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => removeBatch(batch)}
                      disabled={batchBusyId === batch.id}
                      className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                    >
                      {batchBusyId === batch.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {batches.length === 0 && (
              <tr><td colSpan={5} className="p-4 text-center text-slate-400">No group batches yet.</td></tr>
            )}
          </tbody>
        </table>
        </div>
      </div>
      )}
    </div>
  );
}
