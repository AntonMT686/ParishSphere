import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export interface TenantBranding {
  parish_id: string;
  code: string;
  name: string;
  display_name: string;
  logo_url: string | null;
  primary_color: string | null;
  default_language: string;
  currency: string;
  diocese_name: string;
}

export function useTenantBranding() {
  return useQuery({
    queryKey: ['tenant', 'branding'],
    queryFn: async () => (await api.get<TenantBranding>('/tenant/branding')).data,
    staleTime: 10 * 60_000,
    retry: false,
  });
}
