import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { OfficeBearer, OrgUnit, OrgUnitType, UserLookup } from '@/api/types';
import { useCan } from '@/auth/authStore';
import type { PageRequest } from '@/design-system';

export const orgKeys = { types: ['org', 'types'] as const, units: ['org', 'units'] as const };

export function useOrgTypes() {
  const can = useCan();
  return useQuery({
    queryKey: orgKeys.types,
    queryFn: async () => (await api.get<OrgUnitType[]>('/org-unit-types')).data,
    enabled: can('org_unit.view'),
    staleTime: 5 * 60_000,
  });
}

export interface UnitFilters {
  type?: string;
  q?: string;
  status?: string;
  parent?: string;
}

export async function fetchUnits(req: PageRequest, f: UnitFilters): Promise<Page<OrgUnit>> {
  const params = { ...req, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) };
  return (await api.get<Page<OrgUnit>>('/org-units', { params })).data;
}

export function useUnit(id: string) {
  return useQuery({ queryKey: [...orgKeys.units, 'detail', id], queryFn: async () => (await api.get<OrgUnit>(`/org-units/${id}`)).data });
}

export function useBearers(id: string, history: boolean) {
  return useQuery({
    queryKey: [...orgKeys.units, 'bearers', id, history],
    queryFn: async () =>
      (await api.get<OfficeBearer[]>(`/org-units/${id}/office-bearers`, { params: { include_history: history } })).data,
  });
}

export function useUnitSearch(q: string, type?: string) {
  return useQuery({
    queryKey: [...orgKeys.units, 'search', q, type],
    queryFn: async () => (await api.get<Page<OrgUnit>>('/org-units', { params: { q: q || undefined, type, size: 20, status: 'ACTIVE' } })).data.items,
    staleTime: 30_000,
  });
}

export function useUserLookup(q: string) {
  return useQuery({
    queryKey: ['users', 'lookup', q],
    queryFn: async () => (await api.get<UserLookup[]>('/users/lookup', { params: { q } })).data,
    enabled: q.trim().length >= 2,
    staleTime: 30_000,
  });
}

export function typePath(code: string): string {
  return `/org/${code.toLowerCase()}`;
}
