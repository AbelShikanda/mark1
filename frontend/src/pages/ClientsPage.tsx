import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import PageHeader from '../components/PageHeader';
import { useTableFilters } from '../hooks/useTableFilters';
import { useBatches } from '../hooks/useBatches';
import { ACTION_BTN, BTN_PRIMARY, BTN_SECONDARY, CARD_PAD, INPUT, MUTED, PANEL } from '../ui';
import { isValidPhone } from '../validation';

type Client = {
  id: number;
  name: string;
  number: string;
  category: string | null;
  location: string | null;
  birthdays: string | null;
};

const EMPTY = {
  name: '',
  number: '',
  category: '',
  location: '',
  birthdays: '',
};

/** Render an ISO YYYY-MM-DD birthday as e.g. "12 March 1990"; fall back to raw text. */
function formatBirthday(value: string | null): string {
  if (!value) return '-';
  const parsed = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
}

/** True when the value is an empty string or a valid calendar date (YYYY-MM-DD). */
function isValidBirthday(value: string): boolean {
  if (!value.trim()) return true;
  const parsed = new Date(`${value}T00:00:00`);
  return !Number.isNaN(parsed.getTime()) && value === parsed.toISOString().slice(0, 10);
}

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState(EMPTY.name);
  const [number, setNumber] = useState(EMPTY.number);
  const [category, setCategory] = useState(EMPTY.category);
  const [location, setLocation] = useState(EMPTY.location);
  const [birthdays, setBirthdays] = useState(EMPTY.birthdays);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<'clients' | 'batches'>('clients');

  const { batches, loaded: batchesLoaded, reload: reloadBatches, create: createBatch, update: updateBatch, remove: removeBatch } =
    useBatches('client');
  const [batchName, setBatchName] = useState('');
  const [batchDescription, setBatchDescription] = useState('');
  const [batchMemberIds, setBatchMemberIds] = useState<number[]>([]);
  const [batchSearch, setBatchSearch] = useState('');
  const [editingBatchId, setEditingBatchId] = useState<number | null>(null);
  const [batchSaving, setBatchSaving] = useState(false);
  const [batchBusyId, setBatchBusyId] = useState<number | null>(null);

  const load = async () => {
    try {
      const res = await api.get<Client[]>('/clients');
      setClients(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const table = useTableFilters<Client>(
    clients,
    (client) => [client.name, client.number, client.category, client.location].filter(Boolean).join(' '),
    [
      { key: 'name', label: 'Name', getValue: (client) => client.name },
      { key: 'number', label: 'Number', getValue: (client) => client.number },
      { key: 'category', label: 'Category', getValue: (client) => client.category ?? '' },
      { key: 'location', label: 'Location', getValue: (client) => client.location ?? '' },
    ],
  );

  const resetForm = () => {
    setName(EMPTY.name);
    setNumber(EMPTY.number);
    setCategory(EMPTY.category);
    setLocation(EMPTY.location);
    setBirthdays(EMPTY.birthdays);
    setEditingId(null);
  };

  const startEdit = (client: Client) => {
    setTab('clients');
    setEditingId(client.id);
    setName(client.name);
    setNumber(client.number);
    setCategory(client.category ?? '');
    setLocation(client.location ?? '');
    // Legacy free-text birthdays can't be shown in a date input; start blank.
    setBirthdays(/^\d{4}-\d{2}-\d{2}$/.test(client.birthdays ?? '') ? client.birthdays! : '');
    setError(null);
    setNotice(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!isValidPhone(number)) {
      setError('Enter a valid WhatsApp number (7-15 digits, optional + and spaces).');
      return;
    }
    if (!isValidBirthday(birthdays)) {
      setError('Birthday must be a valid date (YYYY-MM-DD).');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: name.trim(),
        number: number.trim(),
        category: category || null,
        location: location || null,
        birthdays: birthdays || null,
      };
      if (editingId) {
        await api.patch(`/clients/${editingId}`, payload);
        setNotice('Client updated.');
      } else {
        await api.post('/clients', payload);
        setNotice('Client added.');
      }
      resetForm();
      await load();
      // Keep batch member lists consistent with the latest clients.
      await reloadBatches();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (client: Client) => {
    if (!window.confirm(`Delete client “${client.name}”? This cannot be undone.`)) return;
    setError(null);
    setNotice(null);
    setBusyId(client.id);
    try {
      await api.delete(`/clients/${client.id}`);
      if (editingId === client.id) resetForm();
      await load();
      await reloadBatches();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const batchTable = useTableFilters<(typeof batches)[number]>(
    batches,
    (batch) => [batch.name, batch.description].filter(Boolean).join(' '),
    [{ key: 'name', label: 'Name', getValue: (batch) => batch.name }],
  );

  const searchTerm = batchSearch.trim().toLowerCase();
  const memberOptions = clients.filter((client) => {
    if (!searchTerm) return true;
    return [client.name, client.number, client.category, client.location].some((value) =>
      (value ?? '').toLowerCase().includes(searchTerm),
    );
  });

  const selectAllMembers = () => {
    setBatchMemberIds((prev) => Array.from(new Set([...prev, ...memberOptions.map((client) => client.id)])));
  };
  const clearMemberSelection = () => setBatchMemberIds([]);
  const toggleMember = (id: number) =>
    setBatchMemberIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const resetBatchForm = () => {
    setBatchName('');
    setBatchDescription('');
    setBatchMemberIds([]);
    setBatchSearch('');
    setEditingBatchId(null);
  };

  const startEditBatch = (batch: (typeof batches)[number]) => {
    setTab('batches');
    setEditingBatchId(batch.id);
    setBatchName(batch.name);
    setBatchDescription(batch.description ?? '');
    setBatchMemberIds(batch.ids);
    setBatchSearch('');
    setError(null);
    setNotice(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const saveBatch = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!batchName.trim()) {
      setError('Give the client batch a name.');
      return;
    }
    if (batchMemberIds.length === 0) {
      setError('Select at least one client for this batch.');
      return;
    }
    setBatchSaving(true);
    try {
      if (editingBatchId) {
        await updateBatch(editingBatchId, batchName.trim(), batchDescription.trim(), batchMemberIds);
        setNotice('Client batch updated.');
      } else {
        await createBatch(batchName.trim(), batchDescription.trim(), batchMemberIds);
        setNotice('Client batch created.');
      }
      resetBatchForm();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBatchSaving(false);
    }
  };

  const deleteBatch = async (batch: (typeof batches)[number]) => {
    if (!window.confirm(`Delete client batch “${batch.name}”? This cannot be undone.`)) return;
    setError(null);
    setBatchBusyId(batch.id);
    try {
      await removeBatch(batch.id);
      if (editingBatchId === batch.id) resetBatchForm();
      setNotice('Client batch deleted.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBatchBusyId(null);
    }
  };

  const columns: DataTableColumn<Client>[] = [
    { key: 'name', header: 'Name', filter: { type: 'text', placeholder: 'Filter name' }, cell: (c) => <span className="font-medium">{c.name}</span> },
    {
      key: 'number',
      header: 'Number',
      filter: { type: 'text', placeholder: 'Filter number' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (c) => c.number,
    },
    {
      key: 'category',
      header: 'Category',
      filter: { type: 'text', placeholder: 'Filter category' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (c) => c.category ?? '-',
    },
    {
      key: 'location',
      header: 'Location',
      filter: { type: 'text', placeholder: 'Filter location' },
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (c) => c.location ?? '-',
    },
    {
      key: 'birthday',
      header: 'Birthday',
      cellClassName: 'text-xs text-slate-500 dark:text-[#a3a3a3]',
      cell: (c) => formatBirthday(c.birthdays),
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (c) => (
        <div className="flex flex-wrap gap-2">
          <button onClick={() => startEdit(c)} className={ACTION_BTN}>
            Edit
          </button>
          <button
            onClick={() => remove(c)}
            disabled={busyId === c.id}
            className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
          >
            {busyId === c.id ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      ),
    },
  ];

  const batchColumns: DataTableColumn<(typeof batches)[number]>[] = [
    {
      key: 'name',
      header: 'Batch',
      filter: { type: 'text', placeholder: 'Filter batch' },
      cell: (batch) => (
        <div>
          <div className="font-medium">{batch.name}</div>
          {batch.description && <div className="text-xs text-slate-500 dark:text-[#a3a3a3]">{batch.description}</div>}
        </div>
      ),
    },
    { key: 'count', header: 'Clients', cellClassName: 'text-xs', cell: (batch) => batch.itemCount },
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
          <button onClick={() => startEditBatch(batch)} className={ACTION_BTN}>
            Edit
          </button>
          <button
            onClick={() => deleteBatch(batch)}
            disabled={batchBusyId === batch.id}
            className="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
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
        : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-[#a3a3a3] dark:hover:text-neutral-100'
    }`;

  return (
    <div className="space-y-4">
      <PageHeader title="Clients / Individuals" description="Manage contacts and reusable client batches." />
      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="flex items-start justify-between rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-emerald-700 hover:underline dark:text-emerald-200">
            Dismiss
          </button>
        </div>
      )}

      <div className="sticky top-0 z-20 -mx-4 flex gap-1 border-b border-slate-200 bg-gray-50/95 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6 dark:border-[#222] dark:bg-black/90">
        <button type="button" onClick={() => setTab('clients')} className={tabClass(tab === 'clients')}>
          Clients <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-[#161616] dark:text-[#a3a3a3]">{clients.length}</span>
        </button>
        <button type="button" onClick={() => setTab('batches')} className={tabClass(tab === 'batches')}>
          Client batches <span className="ml-1 rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200">{batches.length}</span>
        </button>
      </div>

      {tab === 'clients' && (
        <>
          <div className={CARD_PAD}>
            <form onSubmit={save} className="grid grid-cols-1 gap-3 md:grid-cols-6">
              <input className={INPUT} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
              <input className={INPUT} type="tel" inputMode="tel" placeholder="WhatsApp number (e.g. +1 555 123 4567)" value={number} onChange={(e) => setNumber(e.target.value)} />
              <input className={INPUT} placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
              <input className={INPUT} placeholder="Location (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
              <label className="flex flex-col gap-1">
                <span className={`text-xs ${MUTED}`}>Birthday (optional)</span>
                <input
                  type="date"
                  className={INPUT}
                  value={birthdays}
                  min="1900-01-01"
                  max={new Date().toISOString().slice(0, 10)}
                  onChange={(e) => setBirthdays(e.target.value)}
                />
              </label>
              <div className="flex gap-2">
                <button className={`${BTN_PRIMARY} flex-1`} disabled={saving || !name || !number}>
                  {saving ? 'Saving…' : editingId ? 'Save changes' : 'Add client'}
                </button>
                {editingId && (
                  <button type="button" onClick={resetForm} className={BTN_SECONDARY}>
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </div>

          <TableToolbar
            search={table.search}
            onSearch={table.setSearch}
            placeholder="Search name, number, category or location"
            count={table.count}
            total={table.total}
            onClear={table.clearFilters}
            isFiltered={table.isFiltered}
          />

          <DataTable
            columns={columns}
            rows={table.filtered}
            rowKey={(c) => c.id}
            filters={table.values}
            onFilterChange={table.setFilter}
            emptyMessage={clients.length === 0 ? 'No clients yet.' : 'No clients match the current filters.'}
            rowClassName={(c) => (editingId === c.id ? 'bg-indigo-50/60 dark:bg-indigo-950/30' : '')}
            minWidth="760px"
          />
        </>
      )}

      {tab === 'batches' && (
        <div className="space-y-4">
          <div className={PANEL}>
            <div className="p-4">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-[#f5f5f5]">Client batches</h2>
              <p className={`mt-1 text-xs ${MUTED}`}>
                Reusable selections of clients. Batch membership edits apply the next time a run resolves clients.
              </p>
            </div>

            <form onSubmit={saveBatch} className="space-y-3 border-t border-slate-200 p-4 dark:border-[#222]">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <input className={INPUT} placeholder="Batch name" value={batchName} onChange={(e) => setBatchName(e.target.value)} />
                <input className={INPUT} placeholder="Description (optional)" value={batchDescription} onChange={(e) => setBatchDescription(e.target.value)} />
              </div>

              <div className={`flex flex-wrap items-center gap-2 text-xs ${MUTED}`}>
                <input
                  className={`${INPUT} min-w-[220px] flex-1`}
                  placeholder="Search clients by name, number, category or location"
                  value={batchSearch}
                  onChange={(e) => setBatchSearch(e.target.value)}
                />
                <button type="button" className="text-indigo-600 hover:underline dark:text-indigo-400" onClick={selectAllMembers}>
                  Select all
                </button>
                <button type="button" className="text-slate-500 hover:underline dark:text-[#a3a3a3]" onClick={clearMemberSelection}>
                  Clear
                </button>
                <span className="font-medium text-slate-700 dark:text-[#e5e5e5]">{batchMemberIds.length} selected</span>
              </div>

              <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200 p-2 dark:border-[#222]">
                {memberOptions.length === 0 && <div className="p-2 text-xs text-slate-400 dark:text-[#737373]">No clients match this search.</div>}
                {memberOptions.map((client) => (
                  <label key={client.id} className="flex items-center justify-between gap-2 rounded-md px-1 py-1 text-sm hover:bg-slate-50 dark:hover:bg-[#111]">
                    <span className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={batchMemberIds.includes(client.id)}
                        onChange={() => toggleMember(client.id)}
                      />
                      <span>{client.name}</span>
                      <span className="text-xs text-slate-400 dark:text-[#737373]">{client.number}</span>
                    </span>
                    <span className="flex flex-wrap justify-end gap-1 text-[10px]">
                      {client.category && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600 dark:bg-[#161616] dark:text-[#a3a3a3]">{client.category}</span>}
                    </span>
                  </label>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  className={BTN_PRIMARY}
                  disabled={batchSaving || !batchName.trim() || batchMemberIds.length === 0}
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
          </div>

          <TableToolbar
            search={batchTable.search}
            onSearch={batchTable.setSearch}
            placeholder="Search client batches…"
            count={batchTable.count}
            total={batchTable.total}
            onClear={batchTable.clearFilters}
            isFiltered={batchTable.isFiltered}
          />
          <DataTable
            columns={batchColumns}
            rows={batchTable.filtered}
            rowKey={(batch) => batch.id}
            filters={batchTable.values}
            onFilterChange={batchTable.setFilter}
            emptyMessage={batchesLoaded ? 'No client batches yet.' : 'Loading client batches…'}
            minWidth="620px"
            rowClassName={(batch) => (editingBatchId === batch.id ? 'bg-indigo-50/60 dark:bg-indigo-950/30' : '')}
          />
        </div>
      )}
    </div>
  );
}
