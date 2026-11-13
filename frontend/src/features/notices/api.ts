import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { Notice, NoticeListItem } from '@/api/types';
import type { PageRequest } from '@/design-system';

export const noticeKeys = { all: ['notices'] as const };
export const CATEGORIES = ['WEEKLY', 'ANNOUNCEMENT', 'EVENT', 'EMERGENCY', 'DIOCESE', 'NEWS'] as const;
export const STATES = ['DRAFT', 'IN_REVIEW', 'REWORK', 'SCHEDULED', 'LIVE', 'EXPIRED', 'ARCHIVED', 'REJECTED'] as const;

const clean = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined));

export function useBoard(category: string, q: string, size = 50) {
  return useQuery({
    queryKey: [...noticeKeys.all, 'board', category, q, size],
    queryFn: async () => (await api.get<Page<NoticeListItem>>('/notices/board', { params: clean({ category, q, size }) })).data,
  });
}
export async function fetchManaged(req: PageRequest, f: { state?: string; category?: string; q?: string }): Promise<Page<NoticeListItem>> {
  return (await api.get<Page<NoticeListItem>>('/notices', { params: clean({ ...req, ...f }) })).data;
}
export function useNotice(id: string | undefined) {
  return useQuery({
    queryKey: [...noticeKeys.all, id],
    queryFn: async () => (await api.get<Notice>(`/notices/${id}`)).data,
    enabled: Boolean(id),
  });
}

/** Title/body in the reader's language when a Tamil version exists. */
export function localised(n: Pick<NoticeListItem, 'title' | 'title_local'> & { body?: string; body_local?: string | null }, lang: string) {
  const ta = lang === 'ta';
  return {
    title: ta && n.title_local ? n.title_local : n.title,
    body: ta && n.body_local ? n.body_local : n.body,
  };
}

export const CATEGORY_COLOR: Record<string, 'error' | 'primary' | 'secondary' | 'info' | 'success' | 'default'> = {
  EMERGENCY: 'error', WEEKLY: 'primary', EVENT: 'secondary', DIOCESE: 'info', NEWS: 'success', ANNOUNCEMENT: 'default',
};
