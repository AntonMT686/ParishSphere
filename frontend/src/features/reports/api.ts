import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { ReportData, ReportInfo } from '@/api/types';

export const GROUPS = ['PARISH', 'ACTIVITY', 'FINANCE', 'MANAGEMENT'] as const;
export type Params = Record<string, string>;

export function useReportCatalog() {
  return useQuery({ queryKey: ['reports'], queryFn: async () => (await api.get<ReportInfo[]>('/reports')).data, staleTime: 300_000 });
}

export function useReport(code: string, params: Params | null) {
  return useQuery({
    queryKey: ['reports', code, params],
    queryFn: async () => (await api.get<ReportData>(`/reports/${code}`, { params })).data,
    enabled: params !== null,
  });
}

/** Parameters with their defaults, ready to send (empty values dropped). */
export function initialParams(r: ReportInfo): Params {
  const out: Params = {};
  for (const p of r.params) if (p.default) out[p.name] = p.default;
  return out;
}

export function clean(p: Params): Params {
  return Object.fromEntries(Object.entries(p).filter(([, v]) => v !== '' && v != null));
}
