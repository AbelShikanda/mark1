import { useEffect, useMemo, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import PageHeader from '../components/PageHeader';
import { ACTION_BTN, BTN_PRIMARY, BTN_SECONDARY, INPUT, MUTED, NOTICE_INFO, PANEL, SUBTLE } from '../ui';

type FeedbackType = 'bug' | 'improvement' | 'other';
type FeedbackSeverity = 'low' | 'medium' | 'high' | 'critical';
type FeedbackStatus = 'new' | 'triaged' | 'done';

type FeedbackEntry = {
  id: number;
  type: FeedbackType;
  severity: FeedbackSeverity;
  title: string;
  description: string;
  steps: string | null;
  expected: string | null;
  actual: string | null;
  recommended: string | null;
  screenshots: string[];
  status: FeedbackStatus;
  created_at: string | null;
};

const TYPE_LABEL: Record<FeedbackType, string> = {
  bug: 'Bug',
  improvement: 'Improvement',
  other: 'Other',
};

const SEVERITY_STYLE: Record<FeedbackSeverity, string> = {
  low: 'text-slate-500 dark:text-[#a3a3a3]',
  medium: 'text-sky-600 dark:text-sky-400',
  high: 'text-amber-600 dark:text-amber-400',
  critical: 'text-red-600 dark:text-red-400',
};

const STATUS_STYLE: Record<FeedbackStatus, string> = {
  new: 'bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300',
  triaged: 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300',
  done: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
};

const SEVERITY_RANK: Record<FeedbackSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const STATUS_RANK: Record<FeedbackStatus, number> = { new: 0, triaged: 1, done: 2 };

const LABEL = 'block text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]';
const INPUT_LARGE = `${INPUT} w-full px-3 py-2 text-[15px] min-h-[42px]`;

/** Build a markdown issue from a feedback entry, ready to paste anywhere. */
function buildMarkdown(entry: FeedbackEntry): string {
  const kind = TYPE_LABEL[entry.type].toUpperCase();
  const screenshots = entry.screenshots.length
    ? entry.screenshots.map((src, index) => `- ![screenshot-${index + 1}](${src})`).join('\n')
    : '_none_';
  return [
    `## [${kind}] ${entry.title}`,
    '',
    `**Feedback ID:** #${entry.id}`,
    `**Severity:** ${entry.severity}`,
    `**Status:** ${entry.status}`,
    `**Environment:** Marketing Bot v0.3.0 · Windows · submitted ${entry.created_at ?? 'unknown'}`,
    '',
    '### Description',
    entry.description,
    '',
    '### Steps to reproduce',
    entry.steps?.trim() ? entry.steps : '_not provided_',
    '',
    '### Expected',
    entry.expected?.trim() ? entry.expected : '_not provided_',
    '',
    '### Actual',
    entry.actual?.trim() ? entry.actual : '_not provided_',
    '',
    '### Recommended',
    entry.recommended?.trim() ? entry.recommended : '_not provided_',
    '',
    '### Evidence',
    screenshots,
  ].join('\n');
}

export default function FeedbackPage() {
  const [entries, setEntries] = useState<FeedbackEntry[]>([]);
  const [filter, setFilter] = useState<'all' | FeedbackStatus>('all');
  const [sort, setSort] = useState<'newest' | 'oldest' | 'severity' | 'status'>('newest');
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [type, setType] = useState<FeedbackType>('bug');
  const [severity, setSeverity] = useState<FeedbackSeverity>('medium');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [steps, setSteps] = useState('');
  const [expected, setExpected] = useState('');
  const [actual, setActual] = useState('');
  const [recommended, setRecommended] = useState('');
  const [screenshots, setScreenshots] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get<FeedbackEntry[]>('/feedback');
      setEntries(Array.isArray(res.data) ? res.data : []);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const base = filter === 'all' ? [...entries] : entries.filter((entry) => entry.status === filter);
    switch (sort) {
      case 'oldest':
        return base.sort((a, b) => a.id - b.id);
      case 'severity':
        return base.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.id - a.id);
      case 'status':
        return base.sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || b.id - a.id);
      default:
        return base.sort((a, b) => b.id - a.id);
    }
  }, [entries, filter, sort]);

  const resetForm = () => {
    setEditingId(null);
    setType('bug');
    setSeverity('medium');
    setTitle('');
    setDescription('');
    setSteps('');
    setExpected('');
    setActual('');
    setRecommended('');
    setScreenshots([]);
  };

  const startEdit = (entry: FeedbackEntry) => {
    setEditingId(entry.id);
    setType(entry.type);
    setSeverity(entry.severity);
    setTitle(entry.title);
    setDescription(entry.description);
    setSteps(entry.steps ?? '');
    setExpected(entry.expected ?? '');
    setActual(entry.actual ?? '');
    setRecommended(entry.recommended ?? '');
    setScreenshots([...entry.screenshots]);
    setError(null);
    setNotice(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const uploadScreenshot = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post<{ media_url: string }>('/feedback/screenshot', form);
      const url = res.data?.media_url;
      if (!url) throw new Error('Upload failed: the server did not return a URL.');
      setScreenshots((prev) => [...prev, url]);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!title.trim() || !description.trim()) {
      setError('Title and description are required.');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        type,
        severity,
        title: title.trim(),
        description: description.trim(),
        steps: steps.trim() || null,
        expected: expected.trim() || null,
        actual: actual.trim() || null,
        recommended: recommended.trim() || null,
        screenshots,
      };
      if (editingId !== null) {
        await api.put(`/feedback/${editingId}`, payload);
        setNotice(`Feedback #${editingId} updated.`);
      } else {
        await api.post('/feedback', payload);
        setNotice('Feedback submitted. Thank you — it will be attached to the next fix round.');
      }
      resetForm();
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const setStatus = async (entry: FeedbackEntry, status: FeedbackStatus) => {
    setBusyId(entry.id);
    try {
      await api.patch(`/feedback/${entry.id}`, { status });
      setEntries((prev) => prev.map((item) => (item.id === entry.id ? { ...item, status } : item)));
      if (status === 'done') {
        // Collapse the card to just the title once it's done.
        setCollapsed((prev) => new Set(prev).add(entry.id));
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (entry: FeedbackEntry) => {
    if (!window.confirm(`Delete feedback #${entry.id} (“${entry.title}”)?`)) return;
    setBusyId(entry.id);
    try {
      await api.delete(`/feedback/${entry.id}`);
      setEntries((prev) => prev.filter((item) => item.id !== entry.id));
      setNotice(`Feedback #${entry.id} deleted.`);
      if (editingId === entry.id) resetForm();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const copyMarkdown = async (entry: FeedbackEntry) => {
    const markdown = buildMarkdown(entry);
    try {
      await navigator.clipboard.writeText(markdown);
    } catch {
      const area = document.createElement('textarea');
      area.value = markdown;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand('copy');
      } catch {
        setError('Could not copy automatically — select the text below and copy it manually.');
        document.body.removeChild(area);
        return;
      }
      document.body.removeChild(area);
    }
    setCopiedId(entry.id);
    setNotice('Markdown issue copied to the clipboard.');
    window.setTimeout(() => setCopiedId((current) => (current === entry.id ? null : current)), 2000);
  };

  const toggleCollapsed = (id: number) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Feedback" description="Report bugs or suggest improvements. Screenshots welcome — the copy button exports a ready-to-paste markdown issue." />

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className={`flex items-start justify-between ${NOTICE_INFO}`}>
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-blue-600 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,6fr)_minmax(0,6fr)]">
        {/* Submission / edit form */}
        <form onSubmit={save} className={`${PANEL} space-y-3 p-4`}>
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{editingId !== null ? `Edit feedback #${editingId}` : 'New feedback'}</h2>
            {editingId !== null && (
              <button type="button" onClick={resetForm} className="text-xs text-slate-500 hover:text-slate-700 dark:text-[#a3a3a3] dark:hover:text-white">
                Cancel edit
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1">
              <span className={LABEL}>Type</span>
              <select className={INPUT_LARGE} value={type} onChange={(e) => setType(e.target.value as FeedbackType)}>
                <option value="bug">Bug</option>
                <option value="improvement">Improvement</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className={LABEL}>Severity</span>
              <select className={INPUT_LARGE} value={severity} onChange={(e) => setSeverity(e.target.value as FeedbackSeverity)}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </label>
          </div>

          <label className="block space-y-1">
            <span className={LABEL}>Title</span>
            <input className={INPUT_LARGE} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Short summary of the problem or idea" />
          </label>

          <label className="block space-y-1">
            <span className={LABEL}>Description</span>
            <textarea className={`${INPUT_LARGE} min-h-[110px]`} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What is happening, and what do you see?" />
          </label>

          <label className="block space-y-1">
            <span className={LABEL}>Steps to reproduce</span>
            <textarea className={`${INPUT_LARGE} min-h-[72px] font-mono text-[13px]`} value={steps} onChange={(e) => setSteps(e.target.value)} placeholder={'1. Open the Groups page\n2. Click Unsilence\n3. ...'} />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="block space-y-1">
              <span className={LABEL}>Expected</span>
              <textarea className={`${INPUT_LARGE} min-h-[64px]`} value={expected} onChange={(e) => setExpected(e.target.value)} placeholder="What should happen" />
            </label>
            <label className="block space-y-1">
              <span className={LABEL}>Actual</span>
              <textarea className={`${INPUT_LARGE} min-h-[64px]`} value={actual} onChange={(e) => setActual(e.target.value)} placeholder="What actually happened" />
            </label>
          </div>

          <label className="block space-y-1">
            <span className={LABEL}>Recommended solution</span>
            <textarea className={`${INPUT_LARGE} min-h-[64px]`} value={recommended} onChange={(e) => setRecommended(e.target.value)} placeholder="What do you think should be done instead?" />
          </label>

          <div className="space-y-1">
            <span className={LABEL}>Screenshots</span>
            <input
              type="file"
              accept="image/*"
              multiple
              className="block w-full text-xs text-slate-500 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs dark:file:border-[#2a2a2a] dark:file:bg-[#161616] dark:file:text-[#e5e5e5]"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                files.forEach((file) => uploadScreenshot(file));
                e.target.value = '';
              }}
            />
            {uploading && <p className={`text-xs ${SUBTLE}`}>Uploading…</p>}
            {screenshots.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {screenshots.map((src) => (
                  <span key={src} className="relative inline-block">
                    <a href={src} target="_blank" rel="noreferrer">
                      <img src={src} alt="feedback screenshot" className="h-16 w-16 rounded border border-slate-200 object-cover dark:border-[#2a2a2a]" />
                    </a>
                    <button
                      type="button"
                      onClick={() => setScreenshots((prev) => prev.filter((item) => item !== src))}
                      title="Remove screenshot"
                      className="absolute -right-2 -top-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-slate-700 text-[10px] text-white hover:bg-slate-600"
                      aria-label="Remove screenshot"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <button type="submit" className={`${BTN_PRIMARY} w-full text-base py-2.5`} disabled={saving}>
            {saving ? (editingId !== null ? 'Saving…' : 'Submitting…') : editingId !== null ? 'Save changes' : 'Submit feedback'}
          </button>
        </form>

        {/* Submitted items */}
        <div className={`${PANEL} flex flex-col p-4`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2 dark:border-[#222]">
            <h2 className="text-sm font-semibold">Submitted ({filtered.length})</h2>
            <div className="flex flex-wrap items-center gap-2">
              <select className={`${INPUT} text-xs`} value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label="Sort feedback">
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                <option value="severity">Severity (critical → low)</option>
                <option value="status">Status (new → done)</option>
              </select>
              <div className="flex items-center gap-1" role="group" aria-label="Filter by status">
                {(['all', 'new', 'triaged', 'done'] as const).map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setFilter(key)}
                    aria-pressed={filter === key}
                    className={`${ACTION_BTN} ${filter === key ? 'border-slate-400 bg-slate-100 dark:border-[#3a3a3a] dark:bg-[#1a1a1a]' : 'border-slate-300 dark:border-[#2a2a2a]'}`}
                  >
                    {key === 'all' ? 'All' : key[0].toUpperCase() + key.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="mt-3 max-h-[64vh] space-y-3 overflow-y-auto pr-1">
            {loading ? (
              <p className={`text-sm ${MUTED}`}>Loading…</p>
            ) : filtered.length === 0 ? (
              <p className={`text-sm ${MUTED}`}>Nothing here yet. Submit the first item on the left.</p>
            ) : (
              filtered.map((entry) => {
                const isCollapsed = collapsed.has(entry.id);
                return (
                  <article key={entry.id} className="rounded-md border border-slate-200 p-3 dark:border-[#222] dark:bg-[#111]">
                    <button type="button" onClick={() => toggleCollapsed(entry.id)} className="flex w-full items-center justify-between gap-2 text-left" aria-expanded={!isCollapsed}>
                      <span className="min-w-0">
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                          {isCollapsed ? '▸ ' : '▾ '}#{entry.id} · {entry.type}
                        </span>
                        <h3 className="text-sm font-semibold leading-snug text-slate-800 dark:text-[#e5e5e5]">{entry.title}</h3>
                      </span>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${STATUS_STYLE[entry.status]}`}>
                        {entry.status}
                      </span>
                    </button>

                    {!isCollapsed && (
                      <>
                        <p className={`mt-1 text-[11px] leading-snug ${SEVERITY_STYLE[entry.severity]}`}>
                          <span className="font-semibold uppercase">{entry.severity}</span> · {entry.created_at ?? ''}
                        </p>
                        <p className="mt-1 whitespace-pre-wrap text-xs text-slate-600 dark:text-[#a3a3a3]">{entry.description}</p>
                        {entry.recommended?.trim() && (
                          <p className="mt-1 text-[11px] text-slate-500 dark:text-[#a3a3a3]">
                            <span className="font-semibold text-slate-600 dark:text-[#d4d4d4]">Recommended:</span> {entry.recommended}
                          </p>
                        )}

                        {entry.screenshots.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            {entry.screenshots.map((src) => (
                              <a key={src} href={src} target="_blank" rel="noreferrer">
                                <img src={src} alt="attachment" className="h-12 w-12 rounded border border-slate-200 object-cover dark:border-[#2a2a2a]" />
                              </a>
                            ))}
                          </div>
                        )}

                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <button type="button" onClick={() => copyMarkdown(entry)} className={`${BTN_SECONDARY} text-xs ${copiedId === entry.id ? 'border-emerald-400 text-emerald-600 dark:text-emerald-300' : ''}`}>
                            {copiedId === entry.id ? 'Copied ✓' : 'Copy as Markdown'}
                          </button>
                          <button type="button" onClick={() => startEdit(entry)} className={`${ACTION_BTN} border-sky-300 text-sky-700 hover:bg-sky-50 dark:border-sky-800 dark:text-sky-300 dark:hover:bg-sky-950/50`}>
                            Edit
                          </button>
                          {entry.status !== 'triaged' && (
                            <button type="button" onClick={() => setStatus(entry, 'triaged')} disabled={busyId === entry.id} className={`${ACTION_BTN} border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/40`}>
                              Mark triaged
                            </button>
                          )}
                          {entry.status !== 'done' && (
                            <button type="button" onClick={() => setStatus(entry, 'done')} disabled={busyId === entry.id} className={`${ACTION_BTN} border-emerald-300 text-emerald-700 hover:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40`}>
                              Mark done
                            </button>
                          )}
                          {entry.status !== 'new' && (
                            <button type="button" onClick={() => setStatus(entry, 'new')} disabled={busyId === entry.id} className={`${ACTION_BTN} border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-[#2a2a2a] dark:text-[#a3a3a3]`}>
                              Reopen
                            </button>
                          )}
                          <button type="button" onClick={() => remove(entry)} disabled={busyId === entry.id} className="ml-auto text-[11px] text-red-500 hover:text-red-400">
                            Delete
                          </button>
                        </div>
                      </>
                    )}
                  </article>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
