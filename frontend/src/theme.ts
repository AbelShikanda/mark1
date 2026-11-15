import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';
const EVENT = 'app-theme-change';

export function getTheme(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // localStorage can be unavailable in hardened browser contexts.
  }
  return 'dark';
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.documentElement.style.colorScheme = theme;
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Persisting is best effort; the in-memory state still works.
  }
  window.dispatchEvent(new CustomEvent<Theme>(EVENT, { detail: theme }));
}

export function setTheme(theme: Theme): void {
  applyTheme(theme);
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  return next;
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof document !== 'undefined') {
      return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
    }
    return getTheme();
  });

  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail;
      if (detail === 'light' || detail === 'dark') setThemeState(detail);
    };
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);

  return {
    theme,
    isDark: theme === 'dark',
    setTheme: (next: Theme) => {
      applyTheme(next);
      setThemeState(next);
    },
    toggle: () => {
      const next: Theme = theme === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      setThemeState(next);
    },
  };
}
