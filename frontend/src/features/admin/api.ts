import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { AssignmentOut, PermissionModule, Role, RoleSummary, UserOut } from '@/api/types';
import type { PageRequest } from '@/design-system';

export interface UserFilters {
  q?: string;
  role?: string;
  is_active?: boolean;
}

export async function fetchUsers(req: PageRequest, f: UserFilters): Promise<Page<UserOut>> {
  const params = { ...req, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '' && v !== undefined)) };
  return (await api.get<Page<UserOut>>('/users', { params })).data;
}

export function useRoles(enabled = true) {
  return useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get<RoleSummary[]>('/roles')).data,
    enabled,
    staleTime: 60_000,
  });
}

export function useRole(id: string) {
  return useQuery({ queryKey: ['roles', id], queryFn: async () => (await api.get<Role>(`/roles/${id}`)).data });
}

export function usePermissionCatalog() {
  return useQuery({
    queryKey: ['permissions'],
    queryFn: async () => (await api.get<PermissionModule[]>('/permissions')).data,
    staleTime: 5 * 60_000,
  });
}

export function useUser(id: string | null) {
  return useQuery({
    queryKey: ['users', 'detail', id],
    queryFn: async () => (await api.get<UserOut>(`/users/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useUserRoles(id: string | null, history: boolean) {
  return useQuery({
    queryKey: ['users', 'roles', id, history],
    queryFn: async () =>
      (await api.get<AssignmentOut[]>(`/users/${id}/roles`, { params: { include_history: history } })).data,
    enabled: Boolean(id),
  });
}
