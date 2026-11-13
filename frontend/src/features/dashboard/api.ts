import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { Dashboard } from '@/api/types';

export const dashKeys = { all: ['dashboard'] as const };

/** Permission-driven dashboard: only the sections the user may see are present. */
export function useDashboard() {
  return useQuery({
    queryKey: dashKeys.all,
    queryFn: async () => (await api.get<Dashboard>('/dashboard')).data,
    staleTime: 60_000,
  });
}

/** "2026-11" → "Nov 2026" (or "Nov" when short). */
export function monthLabel(key: string, short = false): string {
  const [y, m] = key.split('-').map(Number);
  return new Date(y!, (m ?? 1) - 1, 1).toLocaleDateString('en-IN', short ? { month: 'short' } : { month: 'short', year: 'numeric' });
}
