import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { api } from '@/api/client';
import type { SearchResult } from '@/api/types';

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Global search: grouped, permission-scoped matches (needs at least 2 characters). */
export function useSearch(q: string, opts: { limit?: number; group?: string; enabled?: boolean } = {}) {
  const term = q.trim();
  return useQuery({
    queryKey: ['search', term, opts.limit ?? 5, opts.group ?? ''],
    queryFn: async () => (await api.get<SearchResult>('/search', { params: { q: term, limit: opts.limit ?? 5, group: opts.group || undefined } })).data,
    enabled: term.length >= 2 && opts.enabled !== false,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
