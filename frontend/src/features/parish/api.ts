import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { Clergy, ParishProfile, Priest } from '@/api/types';
import type { PageRequest } from '@/design-system';

export const parishKeys = { profile: ['parish', 'profile'] as const, clergy: ['parish', 'clergy'] as const, priests: ['priests'] as const };

export function useParishProfile() {
  return useQuery({ queryKey: parishKeys.profile, queryFn: async () => (await api.get<ParishProfile>('/parish/profile')).data });
}
export function useClergy() {
  return useQuery({ queryKey: parishKeys.clergy, queryFn: async () => (await api.get<Clergy>('/parish/clergy')).data, staleTime: 5 * 60_000 });
}
export interface PriestFilters { q?: string; status?: string; serving?: boolean }
export async function fetchPriests(req: PageRequest, f: PriestFilters): Promise<Page<Priest>> {
  const params = Object.fromEntries(Object.entries({ ...req, ...f }).filter(([, v]) => v !== '' && v !== undefined));
  return (await api.get<Page<Priest>>('/priests', { params })).data;
}
export function usePriest(id: string) {
  return useQuery({ queryKey: [...parishKeys.priests, id], queryFn: async () => (await api.get<Priest>(`/priests/${id}`)).data });
}

export const PRIEST_ROLES = ['PARISH_PRIEST', 'ASSISTANT_PRIEST', 'RESIDENT_PRIEST', 'DEACON', 'OTHER'] as const;
export const PRIEST_STATUSES = ['ACTIVE', 'RETIRED', 'DECEASED', 'LEFT'] as const;
export const CURRENCIES = ['INR', 'LKR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'MYR'] as const;
export const TIMEZONES = ['Asia/Kolkata', 'Asia/Colombo', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Kuala_Lumpur', 'Europe/London', 'America/New_York', 'UTC'] as const;
