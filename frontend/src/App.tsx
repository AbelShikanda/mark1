import { useState } from 'react';
import ProductsPage from './pages/ProductsPage';
import GroupsPage from './pages/GroupsPage';
import CampaignsPage from './pages/CampaignsPage';
import AnalyticsPage from './pages/AnalyticsPage';
import LogsPage from './pages/LogsPage';

type Page = 'products' | 'groups' | 'campaigns' | 'analytics' | 'logs';

const ICONS: Record<Page, string> = {
  products: '🛒',
  groups: '👥',
  campaigns: '📤',
  analytics: '📊',
  logs: '📝',
};

const NAV: { key: Page; label: string }[] = [
  { key: 'products', label: 'Products' },
  { key: 'groups', label: 'Groups' },
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'analytics', label: 'Analytics' },
  { key: 'logs', label: 'Logs' },
];

export default function App() {
  const [page, setPage] = useState<Page>('products');

  return (
    <div className="flex h-screen bg-gray-50 text-slate-900">
      <aside className="w-64 bg-slate-800 text-white flex flex-col">
        <div className="p-6 font-bold text-lg flex items-center gap-2">
          📊 Marketing
        </div>
        <nav className="flex-1 px-4 space-y-1">
          {NAV.map((item) => {
            const active = page === item.key;
            return (
              <button
                key={item.key}
                onClick={() => setPage(item.key)}
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
        <div className="p-4 text-xs text-slate-400 border-t border-slate-700">
          Bot API: http://localhost:8000
        </div>
      </aside>

      <main className="flex-1 overflow-auto p-6">
        {page === 'products' && <ProductsPage />}
        {page === 'groups' && <GroupsPage />}
        {page === 'campaigns' && <CampaignsPage />}
        {page === 'analytics' && <AnalyticsPage />}
        {page === 'logs' && <LogsPage />}
      </main>
    </div>
  );
}
