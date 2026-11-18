import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { useBatches, type Batch } from '../hooks/useBatches';
import { ACTION_BTN_NEUTRAL, BTN_PRIMARY, BTN_SECONDARY, CARD_PAD, INPUT, MUTED, SUBTLE } from '../ui';
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

  const { batches, create: createBatch, update: updateBatch, remove: removeBatchApi } = useBatches('group');
  const [batchName, setBatchName] = useState('');
  const [batchDescription, setBatchDescription] = useState('');
  const [batchGroupIds, setBatchGroupIds] = useState<number[]>([]);
  const [batchSearch, setBatchSearch] = useState('');
  const [editingBatchId, setEditingBatchId] = useState<number | null>(null);
  const [batchSaving, setBatchSaving] = useState(false);
  const [batchBusyId, setBatchBusyId] = useState<number | null>(null);

  const load = async () => {
    try {
      const res = await api.get<Group[]>('/groups');
      setGroups(Array.isArray(res.data) ? res.data : []);
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

  const startEditBatch = (batch: Batch) => {
    setView('batches');
    setEditingBatchId(batch.id);
    setBatchName(batch.name);
    setBatchDescription(batch.description ?? '');
    setBatchGroupIds(batch.ids);
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
    try {
      if (editingBatchId) {
        await updateBatch(editingBatchId, batchName.trim(), batchDescription.trim(), batchGroupIds);
      } else {
        await createBatch(batchName.trim(), batchDescription.trim(), batchGroupIds);
      }
      resetBatchForm();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBatchSaving(false);
    }
  };

  const removeBatch = async (batch: Batch) => {
    if (!window.confirm(`Delete group batch “${batch.name}”? This cannot be undone.`)) return;
    setError(null);
    setBatchBusyId(batch.id);
    try {
      await removeBatchApi(batch.id);
      if (editingBatchId === batch.id) resetBatchForm();
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

  const baseGroups = groups.filter((g) => {
    if (filter === 'mine') return Boolean(g.is_my_group);
    if (filter === 'core') return Boolean(g.is_core);
    if (filter === 'inactive') return !g.is_active;
    return true;
  });
  const silencedGroups = groups.filter((g) => Boolean(g.is_silenced));

  const groupsTable = useTableFilters<Group>(
    baseGroups,
    (g) => [g.name, g.category, g.location, g.link].filter(Boolean).join(' '),
    [
      { key: 'name', label: 'Name', getValue: (g) => g.name },
      { key: 'category', label: 'Category', getValue: (g) => g.category ?? '' },
      { key: 'location', label: 'Location', getValue: (g) => g.location ?? '' },
      {
        key: 'tags',
        label: 'Tags',
        type: 'select',
        options: [
          { value: 'mine', label: 'Mine' },
          { value: 'core', label: 'Core' },
          { value: 'active', label: 'Active' },
          { value: 'disabled', label: 'Disabled' },
          { value: 'silenced', label: 'Silenced' },
        ],
        getValue: (g) =>
          [
            g.is_my_group ? 'mine' : '',
            g.is_core ? 'core' : '',
            g.is_active ? 'active' : 'disabled',
            g.is_silenced ? 'silenced' : '',
          ].filter(Boolean).join(' '),
        match: 'contains',
      },
    ],
  );

  const silencedTable = useTableFilters<Group>(
    silencedGroups,
    (g) => [g.name, g.category, g.location, g.silence_reason].filter(Boolean).join(' '),
    [
      { key: 'name', label: 'Group', getValue: (g) => g.name },
      { key: 'category', label: 'Category', getValue: (g) => g.category ?? '' },
      { key: 'location', label: 'Location', getValue: (g) => g.location ?? '' },
    ],
  );

  const batchesTable = useTableFilters<Batch>(
    batches,
    (batch) => [batch.name, batch.description].filter(Boolean).join(' '),
    [{ key: 'batch', label: 'Batch', getValue: (batch) => batch.name }],
  );

  const groupsColumns: DataTableColumn<Group>[] = [
    {
      key: 'name',
      header: 'Name',
      filter: { type: 'text', placeholder: 'Filter name' },
      cell: (g) => (
        <div>
          <div className="font-medium">{g.name}</div>
          {g.link && <div className="max-w-xs truncate text-xs text-indigo-600 dark:text-indigo-400">{g.link}</div>}
          {g.failures > 0 && <div className="text-xs text-orange-600 dark:text-orange-400">{g.failures} consecutive miss(es)</div>}
          {g.is_silenced && <div className="text-xs text-red-600 dark:text-red-400">Silenced: {g.silence_reason ?? 'too many misses'}</div>}
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      filter: { type: 'text', placeholder: 'Filter category' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.category ?? '-',
    },
    {
      key: 'location',
      header: 'Location',
      filter: { type: 'text', placeholder: 'Filter location' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.location ?? '-',
    },
    {
      key: 'posted',
      header: 'Posted today / limit',
      cellClassName: 'text-xs',
      cell: (g) => `${g.isPostedProductToday} / ${g.n}`,
    },
    {
      key: 'misses',
      header: 'Misses',
      cellClassName: 'text-xs',
      cell: (g) => (
        <>
          <div>{g.total_misses ?? 0} total</div>
          {g.last_missed_at && <div className={SUBTLE}>last {g.last_missed_at}</div>}
        </>
      ),
    },
    {
      key: 'tags',
      header: 'Tags',
      filter: {
        type: 'select',
        placeholder: 'All tags',
        options: [
          { value: 'mine', label: 'Mine' },
          { value: 'core', label: 'Core' },
          { value: 'active', label: 'Active' },
          { value: 'disabled', label: 'Disabled' },
          { value: 'silenced', label: 'Silenced' },
        ],
      },
      cell: (g) => (
        <div className="flex flex-wrap gap-1">
          {g.is_my_group && <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200">Mine</span>}
          {g.is_core && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-950/60 dark:text-amber-200">Core</span>}
          {!g.is_active && <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-200">Disabled</span>}
          {g.is_silenced && <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-200">Silenced</span>}
        </div>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (g) => (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => startEdit(g)} className={`${ACTION_BTN_NEUTRAL} border-indigo-300 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950/50`}>
            Edit
          </button>
          {g.is_silenced && (
            <button
              onClick={() => unsilence(g)}
              disabled={busyId === g.id}
              className={`${ACTION_BTN_NEUTRAL} border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/50`}
            >
              {busyId === g.id ? 'Clearing…' : 'Unsilence'}
            </button>
          )}
          <button
            onClick={() => toggleActive(g)}
            disabled={busyId === g.id}
            className={`${ACTION_BTN_NEUTRAL} border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-[#2a2a2a] dark:text-[#e5e5e5] dark:hover:bg-[#161616]`}
          >
            {g.is_active ? 'Disable' : 'Enable'}
          </button>
          <button
            onClick={() => remove(g)}
            disabled={busyId === g.id}
            className={`${ACTION_BTN_NEUTRAL} border-red-300 text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50`}
          >
            {busyId === g.id ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      ),
    },
  ];

  const silencedColumns: DataTableColumn<Group>[] = [
    {
      key: 'name',
      header: 'Group',
      filter: { type: 'text', placeholder: 'Filter group' },
      cell: (g) => (
        <div>
          <div className="font-medium">{g.name}</div>
          {g.link && <div className="max-w-xs truncate text-xs text-indigo-600 dark:text-indigo-400">{g.link}</div>}
          <div className="text-xs text-red-600 dark:text-red-400">{g.silence_reason ?? 'Too many consecutive misses'}</div>
        </div>
      ),
    },
    {
      key: 'category',
      header: 'Category',
      filter: { type: 'text', placeholder: 'Filter category' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.category ?? '-',
    },
    {
      key: 'location',
      header: 'Location',
      filter: { type: 'text', placeholder: 'Filter location' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.location ?? '-',
    },
    {
      key: 'misses',
      header: 'Misses',
      cellClassName: 'text-xs',
      cell: (g) => (
        <>
          <div>{g.total_misses ?? 0} total</div>
          <div className="text-orange-600 dark:text-orange-400">{g.failures ?? 0} consecutive</div>
        </>
      ),
    },
    {
      key: 'silenced',
      header: 'Silenced',
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.silenced_at ?? '-',
    },
    {
      key: 'last_success',
      header: 'Last success',
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (g) => g.last_success_at ?? '-',
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (g) => (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => startEdit(g)} className={`${ACTION_BTN_NEUTRAL} border-indigo-300 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950/50`}>
            Edit
          </button>
          <button
            onClick={() => unsilence(g)}
            disabled={busyId === g.id}
            className={`${ACTION_BTN_NEUTRAL} border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-800 dark:text-emerald-300 dark:hover:bg-emerald-950/50`}
          >
            {busyId === g.id ? 'Clearing…' : 'Unsilence'}
          </button>
          <button
            onClick={() => remove(g)}
            disabled={busyId === g.id}
            className={`${ACTION_BTN_NEUTRAL} border-red-300 text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50`}
          >
            Delete
          </button>
        </div>
      ),
    },
  ];

  const batchColumns: DataTableColumn<Batch>[] = [
    {
      key: 'batch',
      header: 'Batch',
      filter: { type: 'text', placeholder: 'Filter batch' },
      cell: (batch) => (
        <div>
          <div className="font-medium">{batch.name}</div>
          {batch.description && <div className="text-xs text-slate-500 dark:text-[#a3a3a3]">{batch.description}</div>}
        </div>
      ),
    },
    {
      key: 'groups',
      header: 'Groups',
      cellClassName: 'text-xs',
      cell: (batch) => batch.itemCount,
    },
    {
      key: 'campaigns',
      header: 'Used by campaigns',
      cellClassName: 'text-xs',
      cell: (batch) => batch.campaignCount,
    },
    {
      key: 'updated',
      header: 'Updated',
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (batch) => batch.updated_at ?? batch.created_at ?? '—',
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (batch) => (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => startEditBatch(batch)}
            className={`${ACTION_BTN_NEUTRAL} border-indigo-300 text-indigo-700 hover:bg-indigo-50 dark:border-indigo-800 dark:text-indigo-300 dark:hover:bg-indigo-950/50`}
          >
            Edit
          </button>
          <button
            onClick={() => removeBatch(batch)}
            disabled={batchBusyId === batch.id}
            className={`${ACTION_BTN_NEUTRAL} border-red-300 text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50`}
          >
            {batchBusyId === batch.id ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      ),
    },
  ];

  const tabClass = (active: boolean) =>
    `rounded-t border-b-2 px-4 py-2 text-sm font-medium ${
      active
        ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
        : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-[#a3a3a3] dark:hover:text-slate-100'
    }`;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Groups</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="sticky top-0 z-20 -mx-4 flex w-[calc(100%+2rem)] gap-1 border-b border-slate-200 bg-gray-50/95 px-4 py-2 backdrop-blur sm:-mx-6 sm:w-[calc(100%+3rem)] sm:px-6 dark:border-[#222] dark:bg-black/90">
        <button type="button" onClick={() => setView('groups')} className={tabClass(view === 'groups')}>
          Groups <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-[#111] dark:text-[#d4d4d4]">{groups.length}</span>
        </button>
        <button type="button" onClick={() => setView('silenced')} className={tabClass(view === 'silenced')}>
          Silenced <span className="ml-1 rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-200">{silencedGroups.length}</span>
        </button>
        <button type="button" onClick={() => setView('batches')} className={tabClass(view === 'batches')}>
          Group batches <span className="ml-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200">{batches.length}</span>
        </button>
      </div>

      {view === 'groups' && (
        <>
          <div className={CARD_PAD}>
            <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <input className={INPUT} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
              <input className={INPUT} placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
              <input className={INPUT} placeholder="Location / region (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
              <input className={INPUT} type="number" min="1" placeholder="Posts per day (n)" value={n} onChange={(e) => setN(e.target.value)} />
              <input className={`${INPUT} md:col-span-2`} inputMode="url" placeholder="My group link (e.g. chat.whatsapp.com/…)" value={link} onChange={(e) => setLink(e.target.value)} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isMyGroup} onChange={(e) => setIsMyGroup(e.target.checked)} /> My group
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isCore} onChange={(e) => setIsCore(e.target.checked)} /> Core group
              </label>
              <div className="flex gap-2">
                <button className={BTN_PRIMARY} disabled={saving || !name}>
                  {saving ? 'Saving…' : editingId ? 'Save changes' : 'Add group'}
                </button>
                {editingId && (
                  <button type="button" onClick={resetForm} className={BTN_SECONDARY}>
                    Cancel
                  </button>
                )}
              </div>
            </form>
            <p className={`mt-2 text-xs ${MUTED}`}>
              Core groups are prioritised as link sources and excluded as link targets. Only “My groups” with a link are used by link campaigns.
            </p>
            <p className={`mt-2 text-xs ${MUTED}`}>
              The silence threshold and other automation parameters live on the Settings page.
            </p>
          </div>

          <section className="space-y-3">
            <TableToolbar
              search={groupsTable.search}
              onSearch={groupsTable.setSearch}
              placeholder="Search groups by name, category, location, or link…"
              count={groupsTable.count}
              total={groupsTable.total}
              onClear={groupsTable.clearFilters}
              isFiltered={groupsTable.isFiltered}
            >
              <select
                className={`${INPUT} py-2 text-xs`}
                value={filter}
                onChange={(e) => setFilter(e.target.value as typeof filter)}
                aria-label="Group visibility filter"
              >
                <option value="all">All groups</option>
                <option value="mine">My groups</option>
                <option value="core">Core groups</option>
                <option value="inactive">Disabled groups</option>
              </select>
            </TableToolbar>
            <DataTable
              columns={groupsColumns}
              rows={groupsTable.filtered}
              rowKey={(g) => g.id}
              filters={groupsTable.values}
              onFilterChange={groupsTable.setFilter}
              emptyMessage="No groups match the current filters."
              minWidth="760px"
              rowClassName={(g) => (editingId === g.id ? 'bg-indigo-50/60 dark:bg-indigo-950/30' : '')}
            />
          </section>
        </>
      )}

      {view === 'silenced' && (
        <section className="space-y-3">
          <div>
            <h2 className="text-xl font-bold">Silenced groups</h2>
            <p className={`mt-1 text-xs ${MUTED}`}>
              Groups are silenced after repeated consecutive misses and are skipped by campaigns until you clear them.
              Clearing a group resets its consecutive miss count so it becomes eligible again.
            </p>
          </div>

          <TableToolbar
            search={silencedTable.search}
            onSearch={silencedTable.setSearch}
            placeholder="Search silenced groups…"
            count={silencedTable.count}
            total={silencedTable.total}
            onClear={silencedTable.clearFilters}
            isFiltered={silencedTable.isFiltered}
          />
          <DataTable
            columns={silencedColumns}
            rows={silencedTable.filtered}
            rowKey={(g) => g.id}
            filters={silencedTable.values}
            onFilterChange={silencedTable.setFilter}
            emptyMessage="No groups are silenced."
            minWidth="760px"
          />
        </section>
      )}

      {view === 'batches' && (
        <div className="w-full space-y-4">
          <div>
            <h2 className="text-xl font-bold">Group batches</h2>
            <p className={`mt-1 text-xs ${MUTED}`}>
              Reusable, live-linked presets. A campaign that uses a batch always resolves its groups at run time, so
              editing the batch changes every campaign that references it on its next run.
            </p>
          </div>

          <form onSubmit={saveBatch} className={`${CARD_PAD} space-y-3`}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                className={INPUT}
                placeholder="Batch name"
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
              />
              <input
                className={INPUT}
                placeholder="Description (optional)"
                value={batchDescription}
                onChange={(e) => setBatchDescription(e.target.value)}
              />
            </div>

            <div className={`flex flex-wrap items-center gap-2 text-xs ${MUTED}`}>
              <input
                className={`${INPUT} min-w-[220px] flex-1`}
                placeholder="Search groups by name, category or location"
                value={batchSearch}
                onChange={(e) => setBatchSearch(e.target.value)}
              />
              <button type="button" className="text-indigo-600 hover:underline dark:text-indigo-400" onClick={selectAllBatchGroups}>
                Select all
              </button>
              <button type="button" className="text-slate-500 hover:underline dark:text-[#a3a3a3]" onClick={clearBatchGroups}>
                Clear
              </button>
              <span className="font-medium text-slate-700 dark:text-[#e5e5e5]">{batchGroupIds.length} selected</span>
            </div>

            <div className="max-h-64 overflow-y-auto rounded border border-slate-200 p-2 dark:border-[#222]">
              {batchGroupOptions.length === 0 && (
                <div className="p-2 text-xs text-slate-400 dark:text-[#737373]">No groups match this search.</div>
              )}
              {batchGroupOptions.map((g) => (
                <label key={g.id} className="flex items-center justify-between gap-2 rounded px-1 py-1 text-sm hover:bg-slate-50 dark:hover:bg-[#161616]">
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={batchGroupIds.includes(g.id)}
                      onChange={() => toggleBatchGroup(g.id)}
                    />
                    <span>{g.name}</span>
                  </span>
                  <span className="flex flex-wrap justify-end gap-1">
                    {g.is_core && <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-950/60 dark:text-amber-200">Core</span>}
                    {g.is_active ? (
                      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200">Active</span>
                    ) : (
                      <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-200">Disabled</span>
                    )}
                  </span>
                </label>
              ))}
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                className={BTN_PRIMARY}
                disabled={batchSaving || !batchName.trim() || batchGroupIds.length === 0}
              >
                {batchSaving ? 'Saving…' : editingBatchId ? 'Save batch changes' : 'Create batch'}
              </button>
              {editingBatchId && (
                <button type="button" onClick={resetBatchForm} className={BTN_SECONDARY}>
                  Cancel
                </button>
              )}
            </div>
          </form>

          <TableToolbar
            search={batchesTable.search}
            onSearch={batchesTable.setSearch}
            placeholder="Search batches…"
            count={batchesTable.count}
            total={batchesTable.total}
            onClear={batchesTable.clearFilters}
            isFiltered={batchesTable.isFiltered}
          />
          <DataTable
            columns={batchColumns}
            rows={batchesTable.filtered}
            rowKey={(batch) => batch.id}
            filters={batchesTable.values}
            onFilterChange={batchesTable.setFilter}
            emptyMessage="No group batches yet."
            minWidth="620px"
            maxHeight="max-h-[55vh]"
            rowClassName={(batch) => (editingBatchId === batch.id ? 'bg-indigo-50/60 dark:bg-indigo-950/30' : '')}
          />
        </div>
      )}
    </div>
  );
}
