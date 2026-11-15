/** Shared light/dark class presets.
 *
 * Keeping the Tailwind classes in one place makes the theme audit predictable:
 * every surface, border and input has an explicit dark counterpart instead of
 * being patched page by page.
 */

export const APP_SHELL = 'flex h-screen bg-gray-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100';

export const CARD = 'rounded-lg border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900';
export const CARD_PAD = `${CARD} p-4`;
export const PANEL = 'rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900';

export const INPUT =
  'rounded border border-slate-300 bg-white p-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500';

export const BTN_PRIMARY =
  'rounded bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50 dark:bg-indigo-500 dark:hover:bg-indigo-400';

export const BTN_SECONDARY =
  'rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800';

export const MUTED = 'text-slate-500 dark:text-slate-400';
export const SUBTLE = 'text-slate-400 dark:text-slate-500';

export const TABLE_WRAP =
  'w-full overflow-auto rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900';

export const TABLE = 'w-full border-collapse';
export const THEAD_ROW =
  'bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-300';
export const TH = 'sticky top-0 z-20 border-b border-slate-200 bg-slate-100 p-3 dark:border-slate-700 dark:bg-slate-800';
export const FILTER_TH =
  'sticky top-10 z-10 border-b border-slate-200 bg-slate-50 p-2 align-top dark:border-slate-700 dark:bg-slate-800/95';
export const ROW =
  'border-b border-slate-200 hover:bg-slate-50 dark:border-slate-700/80 dark:hover:bg-slate-800/60';
export const TD = 'p-3';

export const FILTER_INPUT =
  'w-full min-w-[90px] rounded border border-slate-300 bg-white px-2 py-1 text-xs font-normal normal-case tracking-normal text-slate-700 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500';

export const EMPTY_CELL = 'p-6 text-center text-slate-400 dark:text-slate-500';

export const NOTICE_INFO =
  'rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200';
export const NOTICE_SUCCESS =
  'rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200';
export const NOTICE_ERROR =
  'rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200';
