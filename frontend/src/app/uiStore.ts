import type { PaletteMode } from '@mui/material';
import { create } from 'zustand';

const MODE_KEY = 'ps.themeMode';

function initialMode(): PaletteMode {
  try {
    const saved = window.localStorage.getItem(MODE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

interface UiState {
  mode: PaletteMode;
  sidebarOpen: boolean;
  toggleMode: () => void;
  setSidebarOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  mode: initialMode(),
  sidebarOpen: false,
  toggleMode: () =>
    set((s) => {
      const mode = s.mode === 'light' ? 'dark' : 'light';
      try {
        window.localStorage.setItem(MODE_KEY, mode);
      } catch {
        /* ignore */
      }
      return { mode };
    }),
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
}));
