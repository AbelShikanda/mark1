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
import ThemeToggle from './components/ThemeToggle';

type Page = 'products' | 'groups' | 'clients' | 'campaigns' | 'live' | 'schedules' | 'analytics' | 'logs' | 'settings';

const ICONS: Record<Page, string> = {
  products: '🛒',
  groups: '👥',
  clients: '👤',
  campaigns: '📤',
  live: '📡',
  schedules: '📅',
  analytics: '📊',
  logs: '📝',
  settings: '⚙️',
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

export default function App() {
  const [page, setPage] = useState<Page>('products');
  const [liveCampaignId, setLiveCampaignId] = useState<number | null>(null);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [connectionOffline, setConnectionOffline] = useState(false);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const res = await api.get<Connection>('/live/connection');
        if (stopped) return;
        setConnection(res.data);
        setConnectionOffline(false);
      } catch {
        if (!stopped) setConnectionOffline(true);
      }
    };
    tick();
    const timer = window.setInterval(tick, 5000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, []);

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
  };

  return (
    <div className="flex h-screen bg-gray-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <aside className="flex w-64 flex-col border-r border-slate-700 bg-slate-800 text-white dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2 p-6 text-lg font-bold">
          📊 Marketing
        </div>
        <nav className="flex-1 px-4 space-y-1">
          {NAV.map((item) => {
            const active = page === item.key;
            return (
              <button
                key={item.key}
                onClick={() => navigate(item.key)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition ${
                  active
                    ? 'bg-indigo-600/20 text-indigo-100 border-r-2 border-indigo-400'
                    : 'hover:bg-slate-700/50 text-slate-300'
                }`}
              >
                <span className="w-6 text-center">{ICONS[item.key]}</span>
                {item.label}
              </button>
            );
          })}
        </nav>
        <div className="space-y-2 border-t border-slate-700 p-4 text-xs text-slate-400">
          <button
            type="button"
            onClick={() => openLive()}
            title={connection?.message ?? connectionLabel}
            className="flex w-full items-center gap-2 text-left hover:text-slate-200"
          >
            <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${CONNECTION_DOT[connectionState] ?? CONNECTION_DOT.unknown}`} />
            <span className="truncate">{connectionLabel}</span>
          </button>
          <div>Bot API: http://localhost:8000</div>
          <div className="flex items-center justify-between gap-2 pt-1">
            <span>Appearance</span>
            <ThemeToggle compact />
          </div>
        </div>
      </aside>

      <main className="flex-1 overflow-auto bg-gray-50 p-6 dark:bg-slate-950">
        {page === 'products' && <ProductsPage />}
        {page === 'groups' && <GroupsPage />}
        {page === 'clients' && <ClientsPage />}
        {page === 'campaigns' && <CampaignsPage onOpenLive={openLive} />}
        {page === 'live' && <LivePage initialCampaignId={liveCampaignId} />}
        {page === 'schedules' && <SchedulesPage />}
        {page === 'analytics' && <AnalyticsPage />}
        {page === 'logs' && <LogsPage />}
        {page === 'settings' && <SettingsPage />}
      </main>
    </div>
  );
}
