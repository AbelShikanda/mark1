import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { BTN_PRIMARY, CARD_PAD, INPUT } from '../ui';
import { isValidPhone } from '../validation';

type Client = {
  id: number;
  name: string;
  number: string;
  category: string | null;
  location: string | null;
  birthdays: string | null;
};

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [category, setCategory] = useState('');
  const [location, setLocation] = useState('');
  const [birthdays, setBirthdays] = useState('');
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    (client) =>
      [client.name, client.number, client.category, client.location].filter(Boolean).join(' '),
    [
      { key: 'name', label: 'Name', getValue: (client) => client.name },
      { key: 'number', label: 'Number', getValue: (client) => client.number },
      { key: 'category', label: 'Category', getValue: (client) => client.category ?? '' },
      { key: 'location', label: 'Location', getValue: (client) => client.location ?? '' },
    ],
  );

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!isValidPhone(number)) {
      setError('Enter a valid WhatsApp number (7-15 digits, optional + and spaces).');
      return;
    }
    setSaving(true);
    try {
      await api.post('/clients', {
        name: name.trim(),
        number: number.trim(),
        category: category || null,
        location: location || null,
        birthdays: birthdays || null,
      });
      setName('');
      setNumber('');
      setCategory('');
      setLocation('');
      setBirthdays('');
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (client: Client) => {
    if (!window.confirm(`Delete client “${client.name}”? This cannot be undone.`)) return;
    setError(null);
    setBusyId(client.id);
    try {
      await api.delete(`/clients/${client.id}`);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const columns: DataTableColumn<Client>[] = [
    { key: 'name', header: 'Name', filter: { type: 'text' }, cell: (c) => <span className="font-medium">{c.name}</span> },
    {
      key: 'number',
      header: 'Number',
      filter: { type: 'text' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (c) => c.number,
    },
    {
      key: 'category',
      header: 'Category',
      filter: { type: 'text' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (c) => c.category ?? '-',
    },
    {
      key: 'location',
      header: 'Location',
      filter: { type: 'text' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (c) => c.location ?? '-',
    },
    {
      key: 'birthday',
      header: 'Birthday',
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (c) => c.birthdays ?? '-',
    },
    {
      key: 'actions',
      header: 'Actions',
      cell: (c) => (
        <button
          onClick={() => remove(c)}
          disabled={busyId === c.id}
          className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
        >
          {busyId === c.id ? 'Deleting…' : 'Delete'}
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Clients / Individuals</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className={CARD_PAD}>
        <form onSubmit={add} className="grid grid-cols-1 gap-3 md:grid-cols-6">
          <input className={INPUT} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={INPUT} type="tel" inputMode="tel" placeholder="WhatsApp number (e.g. +1 555 123 4567)" value={number} onChange={(e) => setNumber(e.target.value)} />
          <input className={INPUT} placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input className={INPUT} placeholder="Location (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
          <input className={INPUT} placeholder="Birthday (optional)" value={birthdays} onChange={(e) => setBirthdays(e.target.value)} />
          <button className={BTN_PRIMARY} disabled={saving || !name || !number}>
            {saving ? 'Saving…' : 'Add client'}
          </button>
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
      />
    </div>
  );
}
