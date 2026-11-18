import { useTheme } from '../theme';

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme();
  const dark = theme === 'dark';
  return (
    <button
      type="button"
      onClick={toggle}
      title={`Switch to ${dark ? 'light' : 'dark'} mode`}
      aria-label={`Switch to ${dark ? 'light' : 'dark'} mode`}
      className={
        compact
          ? 'inline-flex h-8 w-8 items-center justify-center rounded-full border border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-700'
          : 'inline-flex items-center gap-2 rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 dark:border-[#2a2a2a] dark:bg-[#111] dark:text-[#e5e5e5] dark:hover:bg-[#161616]'
      }
    >
      <span aria-hidden>{dark ? '🌙' : '☀️'}</span>
      {!compact && <span>{dark ? 'Dark mode' : 'Light mode'}</span>}
    </button>
  );
}
