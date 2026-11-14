import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
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

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Clients / Individuals</h1>
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="bg-white p-4 rounded-lg border shadow-sm">
        <form onSubmit={add} className="grid grid-cols-1 md:grid-cols-6 gap-3">
          <input className="border rounded p-2" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <input className="border rounded p-2" type="tel" inputMode="tel" placeholder="WhatsApp number (e.g. +1 555 123 4567)" value={number} onChange={(e) => setNumber(e.target.value)} />
          <input className="border rounded p-2" placeholder="Category (optional)" value={category} onChange={(e) => setCategory(e.target.value)} />
          <input className="border rounded p-2" placeholder="Location (optional)" value={location} onChange={(e) => setLocation(e.target.value)} />
          <input className="border rounded p-2" placeholder="Birthday (optional)" value={birthdays} onChange={(e) => setBirthdays(e.target.value)} />
          <button className="bg-indigo-600 text-white px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-50" disabled={saving || !name || !number}>
            {saving ? 'Saving…' : 'Add client'}
          </button>
        </form>
      </div>

      <table className="w-full border-collapse border border-slate-200 rounded-lg">
        <thead>
          <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
            <th className="p-3 border-b">Name</th>
            <th className="p-3 border-b">Number</th>
            <th className="p-3 border-b">Category</th>
            <th className="p-3 border-b">Location</th>
            <th className="p-3 border-b">Birthday</th>
            <th className="p-3 border-b">Actions</th>
          </tr>
        </thead>
        <tbody>
          {clients.map((c) => (
            <tr key={c.id} className="border-b hover:bg-slate-50">
              <td className="p-3">{c.name}</td>
              <td className="p-3 text-slate-500 text-xs">{c.number}</td>
              <td className="p-3 text-slate-500 text-xs">{c.category ?? '-'}</td>
              <td className="p-3 text-slate-500 text-xs">{c.location ?? '-'}</td>
              <td className="p-3 text-slate-500 text-xs">{c.birthdays ?? '-'}</td>
              <td className="p-3">
                <button
                  onClick={() => remove(c)}
                  disabled={busyId === c.id}
                  className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
                >
                  {busyId === c.id ? 'Deleting…' : 'Delete'}
                </button>
              </td>
            </tr>
          ))}
          {clients.length === 0 && (
            <tr><td colSpan={6} className="p-4 text-center text-slate-400">No clients yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
