import { useEffect, useMemo, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';

type SettingType = 'int' | 'float' | 'bool' | 'str';

type SettingDef = {
  key: string;
  label: string;
  description: string;
  type: SettingType;
  default: number | boolean | string;
  min?: number | null;
  max?: number | null;
  category: string;
  unit?: string;
};

type SettingValue = number | boolean | string;

type SettingsResponse = {
  values: Record<string, SettingValue>;
  schema: SettingDef[];
};

type SessionStatus = {
  used: number;
  limit: number;
  session_exists: boolean;
  connected: boolean;
};

export default function SettingsPage() {
  const [schema, setSchema] = useState<SettingDef[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [resetting, setResetting] = useState(false);

  const apply = (defs: SettingDef[], vals: Record<string, SettingValue>) => {
    setSchema(defs);
    setValues(Object.fromEntries(defs.map((def) => [def.key, String(vals[def.key] ?? def.default)])));
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get<SettingsResponse>('/settings');
      const defs = Array.isArray(res.data?.schema) ? res.data.schema : [];
      apply(defs, res.data?.values ?? {});
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const loadSession = async () => {
    try {
      const res = await api.get<SessionStatus>('/session/status');
      setSession(res.data);
    } catch {
      // The session card is supplementary; the settings form stays usable.
    }
  };

  useEffect(() => {
    load();
    loadSession();
  }, []);

  const categories = useMemo(() => {
    const order: string[] = [];
    const grouped = new Map<string, SettingDef[]>();
    for (const def of schema) {
      if (!grouped.has(def.category)) {
        grouped.set(def.category, []);
        order.push(def.category);
      }
      grouped.get(def.category)!.push(def);
    }
    return order.map((name) => ({ name, items: grouped.get(name)! }));
  }, [schema]);

  const update = (key: string, value: string) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);

    const payload: Record<string, SettingValue> = {};
    for (const def of schema) {
      const raw = values[def.key] ?? '';
      if (def.type === 'bool') {
        payload[def.key] = raw === 'true';
        continue;
      }
      if (def.type === 'int' || def.type === 'float') {
        const num = Number(raw);
        if (!Number.isFinite(num)) {
          setError(`${def.label} must be a number.`);
          return;
        }
        payload[def.key] = def.type === 'int' ? Math.trunc(num) : num;
        continue;
      }
      payload[def.key] = raw;
    }

    setSaving(true);
    try {
      const res = await api.patch<SettingsResponse>('/settings', { values: payload });
      const defs = Array.isArray(res.data?.schema) ? res.data.schema : schema;
      apply(defs, res.data?.values ?? payload);
      setNotice('Settings saved. The bot uses them immediately.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const resetToDefaults = () => {
    setValues(Object.fromEntries(schema.map((def) => [def.key, String(def.default)])));
    setNotice('Defaults loaded into the form. Choose “Save settings” to apply them.');
  };

  const resetSavedSession = async () => {
    if (
      !window.confirm(
        'Forget the saved WhatsApp session? The next campaign run will show a QR code to scan.',
      )
    ) {
      return;
    }
    setResetting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<SessionStatus>('/session/reset');
      setSession(res.data);
      setNotice('Saved session cleared. The next campaign run will show a QR code.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-xs text-slate-500">
            Automation parameters. Changes are stored in the database and apply to the next action.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 disabled:opacity-50"
          >
            {loading ? 'Reloading…' : 'Reload'}
          </button>
          <button
            type="button"
            onClick={resetToDefaults}
            disabled={schema.length === 0}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50"
          >
            Load defaults
          </button>
        </div>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Session</h2>
            <p className="mt-1 text-sm text-slate-700">
              Saved session: used{' '}
              <span className="font-semibold">{session?.used ?? 0}</span> of{' '}
              <span className="font-semibold">{session?.limit ?? '—'}</span> runs.
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              {session?.session_exists ? 'A saved WhatsApp profile is present.' : 'No saved WhatsApp profile.'}{' '}
              {session?.connected ? 'WhatsApp is connected.' : 'WhatsApp is not connected.'}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              With “Ask for QR after N runs” set to 1, every campaign run clears the profile and shows a
              fresh QR code.
            </p>
          </div>
          <button
            type="button"
            onClick={resetSavedSession}
            disabled={resetting}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {resetting ? 'Forgetting…' : 'Forget session & show QR'}
          </button>
        </div>
      </section>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="flex items-start justify-between rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-emerald-700 hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {loading && schema.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
          Loading settings…
        </div>
      )}

      <form onSubmit={save} className="space-y-4">
        {categories.map((category) => (
          <section key={category.name} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-3 text-lg font-semibold">{category.name}</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {category.items.map((def) => (
                <label key={def.key} className="block text-sm">
                  <span className="font-medium text-slate-800">{def.label}</span>
                  <div className="mt-1 flex items-center gap-2">
                    {def.type === 'bool' ? (
                      <input
                        type="checkbox"
                        checked={values[def.key] === 'true'}
                        onChange={(e) => update(def.key, e.target.checked ? 'true' : 'false')}
                      />
                    ) : (
                      <input
                        className="w-36 rounded border p-2 text-sm"
                        type="number"
                        step={def.type === 'float' ? '0.1' : '1'}
                        min={def.min ?? undefined}
                        max={def.max ?? undefined}
                        value={values[def.key] ?? ''}
                        onChange={(e) => update(def.key, e.target.value)}
                      />
                    )}
                    {def.unit && <span className="text-xs text-slate-500">{def.unit}</span>}
                  </div>
                  <span className="mt-1 block text-xs text-slate-500">{def.description}</span>
                  <span className="mt-0.5 block text-xs text-slate-400">
                    Default: {String(def.default)}
                    {def.unit ? ` ${def.unit}` : ''}
                  </span>
                </label>
              ))}
            </div>
          </section>
        ))}

        {schema.length > 0 && (
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={saving}
              className="rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
