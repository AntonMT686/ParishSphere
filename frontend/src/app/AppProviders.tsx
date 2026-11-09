import CssBaseline from '@mui/material/CssBaseline';
import { ThemeProvider } from '@mui/material/styles';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError } from '@/api/client';
import { useTenantBranding } from '@/api/tenant';
import { useAuthStore } from '@/auth/authStore';
import { buildTheme, FeedbackProvider } from '@/design-system';
import { useUiStore } from './uiStore';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Never retry client errors (401/403/404/422…); retry transient failures once.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1,
      },
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

/** Restores the session on page load and wipes cached data when the user signs out. */
function AuthLifecycle({ children, skipBootstrap }: { children: ReactNode; skipBootstrap?: boolean }) {
  const qc = useQueryClient();
  const bootstrap = useAuthStore((s) => s.bootstrap);
  const status = useAuthStore((s) => s.status);
  useEffect(() => {
    if (!skipBootstrap) void bootstrap();
  }, [bootstrap, skipBootstrap]);
  useEffect(() => {
    if (status === 'anonymous') {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'tenant' });
    }
  }, [status, qc]);
  return <>{children}</>;
}

export function AppProviders({
  children,
  client,
  skipBootstrap,
}: {
  children: ReactNode;
  client?: QueryClient;
  skipBootstrap?: boolean;
}) {
  const [queryClient] = useState(() => client ?? createQueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <ThemedApp>
        <FeedbackProvider>
          <AuthLifecycle skipBootstrap={skipBootstrap}>{children}</AuthLifecycle>
        </FeedbackProvider>
      </ThemedApp>
    </QueryClientProvider>
  );
}
