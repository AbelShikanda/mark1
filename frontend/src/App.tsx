import { useEffect, useState } from 'react';
import { api } from './api';
import ProductsPage from './pages/ProductsPage';
import GroupsPage from './pages/GroupsPage';
import ClientsPage from './pages/ClientsPage';
import CampaignsPage from './pages/CampaignsPage';
import SchedulesPage from './pages/SchedulesPage';
import AnalyticsPage from './pages/AnalyticsPage';
import LogsPage from './pages/LogsPage';
import LivePage from './pages/LivePage';
import SettingsPage from './pages/SettingsPage';
import FeedbackPage from './pages/FeedbackPage';
import MarketPage from './pages/MarketPage';
import DataflowPage from './pages/DataflowPage';
import ThemeToggle from './components/ThemeToggle';
import { APP_SHELL, MAIN, PAGE, SIDEBAR, SIDEBAR_NAV_ITEM, SIDEBAR_NAV_ITEM_ACTIVE } from './ui';

type Page =
  | 'products'
  | 'groups'
  | 'clients'
  | 'campaigns'
  | 'live'
  | 'schedules'
  | 'analytics'
  | 'logs'
  | 'settings'
  | 'dataflow'
  | 'feedback'
  | 'market';

const ICONS: Record<Page, string> = {
  products: 'P',
  groups: 'G',
  clients: 'C',
  campaigns: 'CM',
  live: 'LV',
  schedules: 'SC',
  analytics: 'AN',
  logs: 'LG',
  settings: 'ST',
  dataflow: 'DF',
  feedback: 'FB',
  market: 'MK',
};

const NAV: { key: Page; label: string }[] = [
  { key: 'products', label: 'Products' },
  { key: 'groups', label: 'Groups' },
  { key: 'clients', label: 'Clients' },
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'live', label: 'Live' },
  { key: 'schedules', label: 'Schedules' },
  { key: 'analytics', label: 'Analytics' },
  { key: 'logs', label: 'Logs' },
  { key: 'dataflow', label: 'Dataflow' },
  { key: 'feedback', label: 'Feedback' },
  { key: 'market', label: 'Market' },
  { key: 'settings', label: 'Settings' },
];

type Connection = { state: string; message: string | null };

const CONNECTION_DOT: Record<string, string> = {
  connected: 'bg-emerald-400',
  launching: 'bg-amber-400',
  loading: 'bg-amber-400',
  reconnecting: 'bg-amber-400',
  waiting_login: 'bg-blue-400',
  waiting_qr: 'bg-blue-400',
  disconnected: 'bg-red-400',
  error: 'bg-red-400',
  stopped: 'bg-slate-400',
  unknown: 'bg-slate-500',
};

const CONNECTION_LABEL: Record<string, string> = {
  connected: 'WhatsApp connected',
  launching: 'WhatsApp launching',
  loading: 'WhatsApp loading',
  reconnecting: 'WhatsApp reconnecting',
  waiting_login: 'WhatsApp login needed',
  waiting_qr: 'WhatsApp QR needed',
  disconnected: 'WhatsApp disconnected',
  error: 'WhatsApp error',
  stopped: 'WhatsApp stopped',
  unknown: 'WhatsApp unknown',
};

const COLLAPSE_KEY = 'sidebar_collapsed';
const DEFAULT_CONNECTION_POLL_MS = 5000;
const CONNECTION_POLL_SETTING = 'connection_poll_ms';

export default function App() {
  const [page, setPage] = useState<Page>('products');
  const [liveCampaignId, setLiveCampaignId] = useState<number | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [connectionOffline, setConnectionOffline] = useState(false);
  const [connectionPollMs, setConnectionPollMs] = useState(DEFAULT_CONNECTION_POLL_MS);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(COLLAPSE_KEY) === '1';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [serverKilled, setServerKilled] = useState(false);

  const killServer = async () => {
    if (!window.confirm(
      'Kill the Marketing Bot server? The WhatsApp browser and backend will stop, and this dashboard will go offline until you start Marketing Bot again from the desktop shortcut.'
    )) return;
    try {
      await api.post('/admin/kill-server');
    } catch {
      // The server may drop the connection while exiting; that is expected.
    }
    setServerKilled(true);
  };

  // Poll the effective poll interval once; fall back to the default when the
  // settings endpoint can't be reached.
  useEffect(() => {
    let stopped = false;
    api
      .get<{ values: Record<string, number | string | boolean> }>('/settings')
      .then((res) => {
        const raw = res.data?.values?.[CONNECTION_POLL_SETTING];
        const value = typeof raw === 'number' ? raw : Number(raw);
        if (!stopped && Number.isFinite(value)) setConnectionPollMs(Math.max(500, Math.min(60000, value)));
      })
      .catch(() => {
        // Keep the default cadence.
      });
    return () => {
      stopped = true;
    };
  }, []);

  useEffect(() => {
    let stopped = false;
    let inFlight = false;
    const tick = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.get<Connection>('/live/connection');
        if (stopped) return;
        setConnection(res.data);
        setConnectionOffline(false);
      } catch {
        if (!stopped) setConnectionOffline(true);
      } finally {
        inFlight = false;
      }
    };
    tick();
    const timer = window.setInterval(tick, connectionPollMs);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [connectionPollMs]);

  // Persist the collapsed preference; the overlay is deliberately session-only.
  useEffect(() => {
    try {
      window.localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
    } catch {
      // localStorage unavailable; state still works.
    }
  }, [collapsed]);

  const connectionState = connectionOffline ? 'unknown' : connection?.state ?? 'unknown';
  const connectionLabel = connectionOffline
    ? 'Bot API unreachable'
    : CONNECTION_LABEL[connection?.state ?? 'unknown'] ?? CONNECTION_LABEL.unknown;

  const openLive = (campaignId?: number) => {
    setLiveCampaignId(campaignId ?? null);
    setPage('live');
  };

  const navigate = (target: Page) => {
    if (target === 'live') setLiveCampaignId(null);
    setPage(target);
    setMobileOpen(false);
  };

  const toggleCompact = () => setCollapsed((value) => !value);

  const sidebarBody = (compact: boolean) => (
    <>
      <div className="flex items-center justify-between gap-2 p-4">
        <div className={`flex items-center gap-2 font-bold ${compact ? 'text-base' : 'text-lg'}`}>
          <span aria-hidden>•</span>
          {!compact && <span>Marketing</span>}
        </div>
        {/* Desktop-only collapse toggle; hidden below md. */}
        <button
          type="button"
          onClick={toggleCompact}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-pressed={collapsed}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="hidden rounded-md p-1.5 text-slate-400 hover:bg-slate-700/60 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 md:inline-flex dark:text-[#a3a3a3] dark:hover:bg-[#161616] dark:hover:text-white"
        >
          <svg viewBox="0 0 20 20" className={`h-5 w-5 transition-transform ${collapsed ? 'rotate-180' : ''}`} fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M12.6 4.6a.75.75 0 01.9 1.2L9.9 10l3.6 4.2a.75.75 0 01-1.13.97L8.27 10.5a.75.75 0 010-1l4.2-4.9a.75.75 0 01.13.05z" clipRule="evenodd" />
          </svg>
        </button>
      </div>
      <nav className="flex-1 space-y-1 px-2 sm:px-3" aria-label="Main navigation">
        {NAV.map((item) => {
          const active = page === item.key;
          return (
            <button
              key={item.key}
              onClick={() => navigate(item.key)}
              aria-current={active ? 'page' : undefined}
              title={compact ? item.label : undefined}
              className={`${active ? SIDEBAR_NAV_ITEM_ACTIVE : SIDEBAR_NAV_ITEM} ${compact ? 'justify-center px-2' : ''}`}
            >
              <span className="w-6 shrink-0 text-center" aria-hidden>{ICONS[item.key]}</span>
              {!compact && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>
      <div
        className={`space-y-2 border-t border-slate-700 p-4 text-xs text-slate-400 dark:border-t-[#1f1f1f] dark:text-[#737373] ${
          compact ? 'items-center' : ''
        }`}
      >
        <button
          type="button"
          onClick={() => openLive()}
          title={connection?.message ?? connectionLabel}
          className={`flex w-full items-center gap-2 text-left transition-colors hover:text-slate-200 dark:hover:text-neutral-200 ${
            compact ? 'justify-center' : ''
          }`}
        >
          <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${CONNECTION_DOT[connectionState] ?? CONNECTION_DOT.unknown}`} />
          {!compact && <span className="truncate">{connectionLabel}</span>}
        </button>
        {!compact && <div>Bot API: http://localhost:8000</div>}
        <div className={`flex items-center gap-2 pt-1 ${compact ? 'justify-center' : 'justify-between'}`}>
          {!compact && <span>Appearance</span>}
          <ThemeToggle compact />
        </div>
        <button
          type="button"
          onClick={killServer}
          title="Kill the Marketing Bot server and close the WhatsApp browser"
          aria-label="Kill the Marketing Bot server"
          className={`flex w-full items-center gap-2 rounded-md border border-red-900/60 bg-red-950/30 px-2 py-1.5 text-red-300 transition-colors hover:bg-red-950/60 hover:text-red-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 ${
            compact ? 'justify-center' : ''
          }`}
        >
          <span aria-hidden>•</span>
          {!compact && <span className="truncate text-left">Kill Server</span>}
        </button>
      </div>
    </>
  );

  if (serverKilled) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-950 p-6 text-center text-slate-200">
        <div className="text-4xl" aria-hidden>•</div>
        <h1 className="text-xl font-semibold">Marketing Bot server stopped</h1>
        <p className="max-w-md text-sm text-slate-400">
          The backend and the WhatsApp browser have been shut down. To start it again,
          double-click the Marketing Bot desktop shortcut, then reload this page.
        </p>
      </div>
    );
  }

  return (
    <div className={APP_SHELL}>
      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Open navigation"
        aria-controls="mobile-sidebar"
        aria-expanded={mobileOpen}
        className="fixed left-2 top-2 z-30 inline-flex rounded-md border border-slate-300/60 bg-white/90 p-2 text-slate-700 shadow-sm backdrop-blur focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 md:hidden dark:border-[#2a2a2a] dark:bg-black/80 dark:text-neutral-200"
      >
        <svg viewBox="0 0 20 20" className="h-5 w-5" fill="currentColor" aria-hidden="true">
          <path d="M3 5h14v2H3zM3 9h14v2H3zM3 13h14v2H3z" />
        </svg>
      </button>

      {/* Mobile overlay sidebar */}
      {mobileOpen && (
        <div id="mobile-sidebar" className="fixed inset-0 z-20 md:hidden" role="dialog" aria-modal="true" aria-label="Site navigation">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 cursor-default bg-black/60"
            onClick={() => setMobileOpen(false)}
          />
          <aside className={`${SIDEBAR} absolute left-0 top-0 h-full w-64 shadow-2xl`}>{sidebarBody(false)}</aside>
        </div>
      )}

      {/* Desktop inline sidebar (fixed at all widths unless collapsed) */}
      <aside
        className={`hidden shrink-0 transition-all duration-200 md:block ${collapsed ? 'w-16' : 'w-64'} ${SIDEBAR}`}
        aria-label="Desktop navigation"
      >
        {sidebarBody(collapsed)}
      </aside>

      <main className={MAIN}>
        <div className={PAGE}>
          {page === 'products' && <ProductsPage />}
          {page === 'groups' && <GroupsPage />}
          {page === 'clients' && <ClientsPage />}
          {page === 'campaigns' && <CampaignsPage onOpenLive={openLive} />}
          {page === 'live' && <LivePage initialCampaignId={liveCampaignId} />}
          {page === 'schedules' && <SchedulesPage />}
          {page === 'analytics' && <AnalyticsPage />}
          {page === 'logs' && <LogsPage />}
          {page === 'dataflow' && <DataflowPage />}
          {page === 'feedback' && <FeedbackPage />}
          {page === 'market' && <MarketPage />}
          {page === 'settings' && <SettingsPage />}
        </div>
      </main>
    </div>
  );
}
