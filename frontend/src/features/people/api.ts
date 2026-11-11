import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { Family, FamilyHistory, FamilyListItem, Member, Membership } from '@/api/types';
import type { PageRequest } from '@/design-system';

export const peopleKeys = { families: ['families'] as const, members: ['members'] as const };

function clean(o: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null));
}

export interface FamilyFilters {
  q?: string;
  anbiyam?: string;
  status?: string;
}
export async function fetchFamilies(req: PageRequest, f: FamilyFilters): Promise<Page<FamilyListItem>> {
  return (await api.get<Page<FamilyListItem>>('/families', { params: clean({ ...req, ...f }) })).data;
}
export function useFamily(id: string) {
  return useQuery({ queryKey: [...peopleKeys.families, 'detail', id], queryFn: async () => (await api.get<Family>(`/families/${id}`)).data });
}
export function useFamilyHistory(id: string) {
  return useQuery({
    queryKey: [...peopleKeys.families, 'history', id],
    queryFn: async () => (await api.get<FamilyHistory>(`/families/${id}/history`)).data,
  });
}

export interface MemberFilters {
  q?: string;
  gender?: string;
  status?: string;
  age_min?: number | '';
  age_max?: number | '';
}
export async function fetchMembers(req: PageRequest, f: MemberFilters): Promise<Page<Member>> {
  return (await api.get<Page<Member>>('/members', { params: clean({ ...req, ...f }) })).data;
}
export function useMember(id: string | null) {
  return useQuery({
    queryKey: [...peopleKeys.members, 'detail', id],
    queryFn: async () => (await api.get<Member>(`/members/${id}`)).data,
    enabled: Boolean(id),
  });
}
export function useMemberMemberships(id: string | null) {
  return useQuery({
    queryKey: [...peopleKeys.members, 'memberships', id],
    queryFn: async () => (await api.get<Membership[]>(`/members/${id}/memberships`)).data,
    enabled: Boolean(id),
  });
}
export function useFamilySearch(q: string) {
  return useQuery({
    queryKey: [...peopleKeys.families, 'search', q],
    queryFn: async () => (await api.get<Page<FamilyListItem>>('/families', { params: { q: q || undefined, size: 20 } })).data.items,
    staleTime: 15_000,
  });
}
export function useMemberSearch(q: string) {
  return useQuery({
    queryKey: [...peopleKeys.members, 'search', q],
    queryFn: async () => (await api.get<Page<Member>>('/members', { params: { q, size: 20 } })).data.items,
    enabled: q.trim().length >= 2,
    staleTime: 15_000,
  });
}
