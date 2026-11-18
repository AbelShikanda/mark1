import { useEffect, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import PageHeader from '../components/PageHeader';
import { ACTION_BTN, BTN_PRIMARY, INPUT, MUTED, NOTICE_INFO, PANEL, SUBTLE } from '../ui';

type ReportRow = {
  id: number;
  title: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  trigger: string;
};

type ReportDetail = ReportRow & {
  body: {
    period: { from: string; to: string };
    scope_campaign_id?: number | null;
    summary: Record<string, number>;
    intents: Record<string, number>;
    sentiments: Record<string, number>;
    top_keywords: Array<[string, number]>;
    top_questions: Array<[string, number]>;
    group_stats: Array<{ id: number; name: string; posts: number; replies: number }>;
    product_stats: Record<string, { id: number; name: string; posts: number; replies: number }>;
    best_hour: number | null;
    best_weekday: string | null;
    best_hour_replies: Record<string, number>;
    spam: { flagged: number };
  };
  summary_md?: string;
};

type ReviewRow = {
  id: number;
  group_id: number | null;
  group_name: string | null;
  sender: string;
  text: string;
  captured_at: string;
  intent: string;
  sentiment: string;
};

type VaultRow = {
  id: number;
  normalized_link: string;
  source: string;
  group_name: string | null;
  first_seen: string;
  last_seen: string;
  seen_count: number;
};

const INTENTS = [
  'price', 'availability', 'order', 'location', 'delivery',
  'complaint', 'compliment', 'greeting', 'other',
] as const;

const TAB = 'rounded-md border px-3 py-1.5 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500';
const TAB_ACTIVE = 'border-indigo-500 bg-indigo-950/40 text-indigo-300';
const TAB_IDLE = 'border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-[#2a2a2a] dark:text-[#a3a3a3] dark:hover:bg-[#161616]';

function bar(label: string, value: number, max: number, tone = 'bg-indigo-500') {
  const width = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div key={label} className="flex items-center gap-2 text-xs">
      <span className="w-36 shrink-0 truncate text-slate-500 dark:text-[#a3a3a3]" title={label}>{label}</span>
      <div className="h-2 flex-1 rounded bg-slate-200 dark:bg-[#222]">
        <div className={`h-2 rounded ${tone}`} style={{ width: `${width}%` }} />
      </div>
      <span className="w-8 text-right font-mono">{value}</span>
    </div>
  );
}

export default function MarketPage() {
  const [tab, setTab] = useState<'reports' | 'review' | 'unclassified' | 'vault'>('reports');
  const [campaigns, setCampaigns] = useState<Array<{ id: number; name: string }>>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [selected, setSelected] = useState<ReportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [review, setReview] = useState<ReviewRow[]>([]);
  const [unclassified, setUnclassified] = useState<ReviewRow[]>([]);
  const [vault, setVault] = useState<VaultRow[]>([]);
  const [days, setDays] = useState('7');
  const [scope, setScope] = useState('all');
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = async () => {
    setError(null);
    try {
      const [rep, rev, unc, vaultRes] = await Promise.all([
        api.get<ReportRow[]>('/market/reports'),
        api.get<ReviewRow[]>('/market/review?limit=100'),
        api.get<ReviewRow[]>('/market/unclassified?limit=100'),
        api.get<VaultRow[]>('/market/vault'),
      ]);
      setReports(Array.isArray(rep.data) ? rep.data : []);
      setReview(Array.isArray(rev.data) ? rev.data : []);
      setUnclassified(Array.isArray(unc.data) ? unc.data : []);
      setVault(Array.isArray(vaultRes.data) ? vaultRes.data : []);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  useEffect(() => {
    load();
    api.get<Array<{ id: number; name: string }>>('/campaigns')
      .then((res) => setCampaigns(Array.isArray(res.data) ? res.data : []))
      .catch(() => setCampaigns([]));
  }, []);

  const openReport = async (id: number) => {
    setDetailLoading(true);
    try {
      const res = await api.get<ReportDetail>(`/market/reports/${id}`);
      setSelected(res.data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  };

  const generate = async () => {
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<ReportDetail>('/market/reports', {
        days: parseInt(days, 10) || 7,
        campaign_id: scope === 'all' ? 'all' : parseInt(scope, 10),
      });
      setNotice('Report generated.');
      setSelected(res.data);
      await load();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setGenerating(false);
    }
  };

  const removeReport = async (id: number) => {
    if (!window.confirm('Delete this report? This cannot be undone.')) return;
    try {
      await api.delete(`/market/reports/${id}`);
      setReports((prev) => prev.filter((report) => report.id !== id));
      if (selected?.id === id) setSelected(null);
      setNotice('Report deleted.');
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const download = (rid: number, kind: 'markdown' | 'csv' | 'pdf') => {
    window.open(`/market/reports/${rid}/${kind}`, '_blank', 'noopener');
  };

  const actOnReview = async (id: number, action: 'spam' | 'clean' | 'keep') => {
    setBusyId(id);
    try {
      await api.post(`/market/review/${id}`, { action });
      setReview((prev) => prev.filter((row) => row.id !== id));
      setNotice(action === 'spam' ? 'Marked as spam.' : action === 'clean' ? 'Marked as clean.' : 'Kept for later.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const labelIntent = async (id: number, intent: string) => {
    setBusyId(id);
    try {
      await api.post(`/market/classify/${id}`, { intent });
      setUnclassified((prev) => prev.filter((row) => row.id !== id));
      setNotice(`Intent set to "${intent}".`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  };

  const removeVaultLink = async (id: number) => {
    if (!window.confirm('Remove this group link from the vault?')) return;
    try {
      await api.delete(`/market/vault/${id}`);
      setVault((prev) => prev.filter((row) => row.id !== id));
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const detail = selected?.body;
  const maxIntent = Math.max(1, ...Object.values(detail?.intents ?? {}));
  const maxKeyword = Math.max(1, ...(detail?.top_keywords ?? []).map((item) => item[1]));
  const maxHour = Math.max(1, ...Object.values(detail?.best_hour_replies ?? {}));
  const bestHour = detail?.best_hour;
  const weekday = detail?.best_weekday;

  return (
    <div className="space-y-4">
      <PageHeader title="Market" description="Reports, spam review and group-link vault from captured WhatsApp messages." />

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className={`flex items-start justify-between ${NOTICE_INFO}`}>
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-blue-600 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100">Dismiss</button>
        </div>
      )}

      <div className="flex gap-2 border-b border-slate-200 pb-2 dark:border-[#222]" role="tablist">
        {(['reports', 'review', 'unclassified', 'vault'] as const).map((key) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`${TAB} ${tab === key ? TAB_ACTIVE : TAB_IDLE}`}
          >
            {key === 'reports' ? 'Reports' : key === 'review' ? `Spam review (${review.length})` : key === 'unclassified' ? `Unclassified (${unclassified.length})` : `Vault (${vault.length})`}
          </button>
        ))}
      </div>

      {tab === 'reports' && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className={`${PANEL} p-4`}>
            <h2 className="text-sm font-semibold">Reports</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select className={INPUT} value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Scope">
                <option value="all">All campaigns</option>
                {campaigns.map((campaign) => (
                  <option key={campaign.id} value={String(campaign.id)}>{campaign.name}</option>
                ))}
              </select>
              <select className={INPUT} value={days} onChange={(e) => setDays(e.target.value)} aria-label="Period">
                <option value="7">Last 7 days</option>
                <option value="30">Last 30 days</option>
                <option value="90">Last 90 days</option>
              </select>
              <button className={BTN_PRIMARY} disabled={generating} onClick={generate}>
                {generating ? 'Generating…' : 'Generate report'}
              </button>
            </div>
            <div className="mt-3 max-h-[68vh] space-y-2 overflow-y-auto">
              {reports.length === 0 ? (
                <p className={`text-sm ${MUTED}`}>No reports yet. Generate one above, or enable automatic weekly reports in Settings.</p>
              ) : (
                reports.map((report) => (
                  <button
                    key={report.id}
                    type="button"
                    onClick={() => openReport(report.id)}
                    className={`block w-full rounded-md border p-2 text-left transition-colors ${
                      selected?.id === report.id
                        ? 'border-indigo-500 bg-indigo-950/30'
                        : 'border-slate-200 hover:bg-slate-50 dark:border-[#222] dark:hover:bg-[#111]'
                    }`}
                  >
                    <div className="truncate text-xs font-semibold text-slate-800 dark:text-[#e5e5e5]">{report.title}</div>
                    <div className={`text-[10px] ${SUBTLE}`}>{report.generated_at} · {report.trigger}</div>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className={`${PANEL} p-4`}>
            {detailLoading ? (
              <p className={`text-sm ${MUTED}`}>Loading report…</p>
            ) : !selected || !detail ? (
              <p className={`text-sm ${MUTED}`}>Select a report on the left, or generate a new one.</p>
            ) : (
              <div className="max-h-[78vh] space-y-4 overflow-y-auto">
                <div className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-200 pb-2 dark:border-[#222]">
                  <div>
                    <h2 className="text-sm font-semibold">{selected.title}</h2>
                    <p className={`text-[11px] ${SUBTLE}`}>{detail.period.from} → {detail.period.to}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button className={ACTION_BTN} onClick={() => download(selected.id, 'markdown')}>MD</button>
                    <button className={ACTION_BTN} onClick={() => download(selected.id, 'csv')}>CSV</button>
                    <button className={ACTION_BTN} onClick={() => download(selected.id, 'pdf')}>PDF</button>
                    <button className="text-xs text-red-500 hover:text-red-400" onClick={() => removeReport(selected.id)}>Delete</button>
                  </div>
                </div>

                {((detail.summary.posts_with_capture ?? 0) === 0 || detail.summary.replies_captured === 0) && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-[11px] text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                    No reply data captured yet. Enable <strong>Capture replies after sending</strong> on a campaign, run it, then regenerate — reply-derived sections below will fill in.
                  </div>
                )}

                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[
                    ['Posts sent', `${detail.summary.posts_sent} (${detail.summary.posts_with_capture} cap)`],
                    ['Replies', detail.summary.replies_captured],
                    ['Msgs / post', detail.summary.messages_per_post],
                    ['Spam flagged', detail.summary.spam_flagged],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-md border border-slate-200 bg-slate-50 p-2 text-center dark:border-[#222] dark:bg-[#111]">
                      <div className={`text-[9px] uppercase tracking-wide ${SUBTLE}`}>{label}</div>
                      <div className="text-lg font-semibold">{value}</div>
                    </div>
                  ))}
                </div>

                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Best time</h3>
                  {bestHour === null || bestHour === undefined ? (
                    <p className="mt-1 text-xs text-slate-500 dark:text-[#a3a3a3]">Not enough captured reply data yet — nothing to rank.</p>
                  ) : (
                    <>
                      <p className="mt-1 text-xs text-slate-600 dark:text-[#a3a3a3]">
                        Best hour of day: {bestHour}:00
                        {weekday ? ` · best weekday: ${weekday}` : ''}
                      </p>
                      <div className="mt-1 space-y-1">
                        {Object.entries(detail.best_hour_replies ?? {})
                          .sort(([a], [b]) => Number(a) - Number(b))
                          .map(([hour, replies]) => bar(`${hour}:00`, Number(replies), maxHour, 'bg-emerald-500'))}
                      </div>
                    </>
                  )}
                </section>

                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Intents</h3>
                  <div className="mt-1 space-y-1">
                    {Object.entries(detail.intents ?? {})
                      .sort(([, a], [, b]) => Number(b) - Number(a))
                      .map(([intent, count]) => bar(intent, Number(count), maxIntent))}
                  </div>
                </section>

                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Top keywords</h3>
                  <div className="mt-1 space-y-1">
                    {(detail.top_keywords ?? []).slice(0, 12).map(([word, count]) => bar(word, Number(count), maxKeyword, 'bg-sky-500'))}
                  </div>
                </section>

                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Groups (by replies)</h3>
                  <table className="mt-1 w-full text-left text-[11px]">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 dark:border-[#222] dark:text-[#a3a3a3]">
                        <th className="py-1">Group</th><th className="py-1 text-right">Posts</th><th className="py-1 text-right">Replies</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detail.group_stats ?? []).slice(0, 15).map((stat) => (
                        <tr key={stat.id} className="border-b border-slate-100 dark:border-[#1a1a1a]">
                          <td className="py-1">{stat.name}</td>
                          <td className="py-1 text-right font-mono">{stat.posts}</td>
                          <td className="py-1 text-right font-mono">{stat.replies}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>

                <section>
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Products (by replies)</h3>
                  <table className="mt-1 w-full text-left text-[11px]">
                    <thead>
                      <tr className="border-b border-slate-200 text-slate-500 dark:border-[#222] dark:text-[#a3a3a3]">
                        <th className="py-1">Product</th><th className="py-1 text-right">Posts</th><th className="py-1 text-right">Replies</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(Object.values(detail.product_stats ?? {}) as ReportDetail['body']['product_stats'][string][])
                        .slice(0, 15)
                        .map((stat) => (
                          <tr key={stat.id} className="border-b border-slate-100 dark:border-[#1a1a1a]">
                            <td className="py-1">{stat.name}</td>
                            <td className="py-1 text-right font-mono">{stat.posts}</td>
                            <td className="py-1 text-right font-mono">{stat.replies}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </section>
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'review' && (
        <section className="space-y-2">
          {review.length === 0 ? (
            <p className={`text-sm ${MUTED}`}>Nothing flagged. New spam/scam messages will appear here.</p>
          ) : (
            review.map((row) => (
              <article key={row.id} className="rounded-md border border-red-200 bg-red-50/60 p-3 text-xs dark:border-red-900/50 dark:bg-red-950/20">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[10px] uppercase tracking-wide text-red-500 dark:text-red-400">#{row.id} · {row.group_name ?? `group ${row.group_id}`} · {row.captured_at}</span>
                  <span className={`text-[10px] ${SUBTLE}`}>{row.sender}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-slate-700 dark:text-[#d4d4d4]">{row.text}</p>
                <div className="mt-2 flex gap-2">
                  <button className={`${ACTION_BTN} border-red-400 text-red-600 hover:bg-red-100 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50`} disabled={busyId === row.id} onClick={() => actOnReview(row.id, 'spam')}>Spam</button>
                  <button className={`${ACTION_BTN} border-emerald-400 text-emerald-600 hover:bg-emerald-50 dark:border-emerald-900 dark:text-emerald-300 dark:hover:bg-emerald-950/40`} disabled={busyId === row.id} onClick={() => actOnReview(row.id, 'clean')}>Clean</button>
                  <button className={`${ACTION_BTN} border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-[#2a2a2a] dark:text-[#a3a3a3]`} disabled={busyId === row.id} onClick={() => actOnReview(row.id, 'keep')}>Keep</button>
                </div>
              </article>
            ))
          )}
        </section>
      )}

      {tab === 'unclassified' && (
        <section className="space-y-2">
          {unclassified.length === 0 ? (
            <p className={`text-sm ${MUTED}`}>Nothing unclassified. Either capture is not yet running on any campaign, or everything classified cleanly.</p>
          ) : (
            unclassified.map((row) => (
              <article key={row.id} className={`${PANEL} p-3 text-xs`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">#{row.id} · {row.group_name ?? `group ${row.group_id}`} · {row.captured_at}</span>
                  <span className={`text-[10px] ${SUBTLE}`}>{row.sender}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap text-slate-700 dark:text-[#d4d4d4]">{row.text}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {INTENTS.map((intent) => (
                    <button
                      key={intent}
                      className={`${ACTION_BTN} border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-[#2a2a2a] dark:text-[#a3a3a3]`}
                      disabled={busyId === row.id}
                      onClick={() => labelIntent(row.id, intent)}
                    >
                      {intent}
                    </button>
                  ))}
                </div>
              </article>
            ))
          )}
        </section>
      )}

      {tab === 'vault' && (
        <section className="space-y-2">
          {vault.length === 0 ? (
            <p className={`text-sm ${MUTED}`}>No group links captured yet. Links in chats you post to are vaulted automatically.</p>
          ) : (
            vault.map((row) => (
              <div key={row.id} className={`${PANEL} flex flex-wrap items-center justify-between gap-2 p-3 text-xs`}>
                <div className="min-w-0">
                  <a href={`https://${row.normalized_link}`} target="_blank" rel="noreferrer" className="block truncate font-mono text-[11px] text-indigo-500 hover:underline">{row.normalized_link}</a>
                  <div className={`text-[10px] ${SUBTLE}`}>{row.group_name ?? 'unknown group'} · seen {row.seen_count}x · first {row.first_seen?.slice(0, 10)} · last {row.last_seen?.slice(0, 10)}</div>
                </div>
                <button className="text-[11px] text-red-500 hover:text-red-400" onClick={() => removeVaultLink(row.id)}>Remove</button>
              </div>
            ))
          )}
        </section>
      )}
    </div>
  );
}
