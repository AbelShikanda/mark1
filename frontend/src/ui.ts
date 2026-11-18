/** Shared light/dark class presets.
 *
 * Single source of truth for the theme: light mode keeps the current look,
 * dark mode is a true-black stack (#000 canvas with layered #0a/#111/#1616
 * surfaces and 1px #222/#2a2a2a borders). Elevation comes from borders, not
 * shadows. Indigo remains the accent.
 *
 * Rule for any future class added here: it must come from a preset, and it
 * must carry an explicit dark counterpart (or inherit one).
 */

export const APP_SHELL = 'flex h-screen bg-gray-50 text-slate-900 dark:bg-black dark:text-neutral-200';

// Z layering scale (literal Tailwind values; keep in sync with Z below).
export const Z = {
  BASE: 0,
  TABLE_FILTER: 10,
  TABLE_HEAD: 20,
  STICKY_BAR: 20,
  OVERLAY: 30,
  MODAL: 40,
} as const;

// Page width policy: main is the only scroll container; inner page content is
// capped at a generous measure and centred on ultra-wide screens.
export const PAGE = 'mx-auto w-full max-w-[1800px]';
// main scrolls; the PAGE wrapper is padded and capped.
export const MAIN = 'flex-1 overflow-auto bg-gray-50 p-4 sm:p-6 dark:bg-black';

// Cards / surfaces
export const CARD = 'rounded-md border border-slate-200 bg-white shadow-sm dark:border-[#222] dark:bg-[#0a0a0a] dark:shadow-none';
export const CARD_PAD = `${CARD} p-4`;
export const PANEL = 'rounded-md border border-slate-200 bg-white dark:border-[#222] dark:bg-[#0a0a0a]';
export const SUBPANEL = 'rounded-md border border-slate-200 bg-slate-50 dark:border-[#222] dark:bg-[#111]';
// Elevation lift for hoverable rows / interactive rows inside panels.
export const ELEVATE = 'transition-colors hover:border-slate-300 dark:hover:border-[#2a2a2a]';

// Inputs
export const INPUT =
  'rounded-md border border-slate-300 bg-white p-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-[#2a2a2a] dark:bg-[#111] dark:text-neutral-100 dark:placeholder:text-neutral-500';

export const BTN_PRIMARY =
  'rounded-md bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700 disabled:opacity-50 dark:bg-indigo-500 dark:text-black dark:hover:bg-indigo-400';

export const BTN_SECONDARY =
  'rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-[#2a2a2a] dark:text-neutral-200 dark:hover:bg-[#161616]';

// Ghost/action buttons used in table rows and toolbars (replaces inline copies).
export const ACTION_BTN =
  'rounded-md border border-indigo-300 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50 disabled:opacity-40 dark:border-indigo-900 dark:text-indigo-300 dark:hover:bg-indigo-950/50';
// Neutral shell for callers that inject their own border/text/hover hues.
export const ACTION_BTN_NEUTRAL = 'rounded-md border px-2 py-1 text-xs disabled:opacity-40';

// Semantic text tones
export const MUTED = 'text-slate-500 dark:text-[#a3a3a3]';
export const SUBTLE = 'text-slate-400 dark:text-[#737373]';
export const FG = 'text-slate-800 dark:text-[#e5e5e5]';

// Table surfaces (sticky layers; keep Z values in sync)
export const TABLE_WRAP =
  'w-full overflow-auto rounded-md border border-slate-200 bg-white dark:border-[#222] dark:bg-[#0a0a0a]';

export const TABLE = 'w-full border-collapse';
export const THEAD_ROW =
  'text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-[#111] dark:text-[#a3a3a3]';
export const TH = 'sticky top-0 z-20 border-b border-slate-200 bg-slate-100 p-3 dark:border-[#2a2a2a] dark:bg-[#111]';
export const FILTER_TH =
  'sticky top-10 z-10 border-b border-slate-200 bg-slate-50 p-2 align-top dark:border-[#222] dark:bg-[#0f0f0f]';
export const ROW =
  'border-b border-slate-200 hover:bg-slate-50 dark:border-b-[#1f1f1f] dark:hover:bg-[#111]';
export const TD = 'p-3';

export const FILTER_INPUT =
  'w-full min-w-[90px] rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-normal normal-case tracking-normal text-slate-700 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none dark:border-[#2a2a2a] dark:bg-[#0a0a0a] dark:text-neutral-100 dark:placeholder:text-neutral-500';

export const EMPTY_CELL = 'p-6 text-center text-slate-400 dark:text-[#737373]';

// Notices
export const NOTICE_INFO =
  'rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/30 dark:text-blue-200';
export const NOTICE_SUCCESS =
  'rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200';
export const NOTICE_ERROR =
  'rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200';

// Sidebar shell
export const SIDEBAR =
  'flex flex-col border-r border-slate-200 bg-slate-800 text-white transition-all duration-200 dark:border-r-[#1f1f1f] dark:bg-[#080808] dark:text-neutral-200';
export const SIDEBAR_NAV_ITEM =
  'flex w-full items-center gap-3 rounded-md px-4 py-2.5 text-sm transition-colors hover:bg-slate-700/50 text-slate-300 dark:hover:bg-[#111] dark:text-[#a3a3a3]';
export const SIDEBAR_NAV_ITEM_ACTIVE =
  'flex w-full items-center gap-3 rounded-md px-4 py-2.5 text-sm bg-indigo-600/15 text-indigo-100 outline outline-1 outline-indigo-500/30 dark:bg-indigo-500/15 dark:text-indigo-200 dark:outline-indigo-500/40';

// Dataflow (canvas) tokens - plain hex for Canvas 2D, mirrors the black stack.
export const DATAFLOW = {
  canvasBg: '#000000',
  canvasGrid: '#1c1c1c',
  nodeFill: '#161616',
  nodeStroke: '#2a2a2a',
  nodeText: '#e5e5e5',
  nodeMuted: '#a3a3a3',
  edgeIdle: '#2a2a2a',
  edgeActive: '#404040',
  healthy: '#34d399', // emerald-400
  warning: '#fbbf24', // amber-400
  error: '#ef4444', // red-500
  info: '#818cf8', // indigo-400
  dot: '#a5b4fc', // indigo-300
  panelSurface: '#0a0a0a',
  panelBorder: '#222222',
  heading: '#f5f5f5',
  body: '#d4d4d4',
  code: '#a3a3a3',
} as const;

/** Dataflow: caps for the canvas renderer. */
export const DATAFLOW_CAPS = {
  MAX_NODES: 50,
  MAX_EDGES: 200,
  MAX_EVENTS: 500,
  SAMPLE_SECONDS: 60,
} as const;
