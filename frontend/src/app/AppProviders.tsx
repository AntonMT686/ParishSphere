import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMemo, useState, type ReactNode } from 'react';
import { useTenantBranding } from '@/api/tenant';
import { buildTheme } from '@/design-system';
import { useUiStore } from './uiStore';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
    },
  });
}

function ThemedApp({ children }: { children: ReactNode }) {
  const mode = useUiStore((s) => s.mode);
  const { data: branding } = useTenantBranding();
  const theme = useMemo(() => buildTheme(mode, branding?.primary_color), [mode, branding?.primary_color]);
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline enableColorScheme />
      {children}
    </ThemeProvider>
  );
}

export function AppProviders({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [queryClient] = useState(() => client ?? createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <ThemedApp>{children}</ThemedApp>
    </QueryClientProvider>
  );
}
