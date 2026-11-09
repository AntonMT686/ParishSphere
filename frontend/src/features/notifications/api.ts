import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { NotificationItem } from '@/api/types';

export const notificationKeys = { all: ['notifications'] as const };

/** Unread count: refreshed on window focus and after actions – never polled (polling would keep idle sessions alive). */
export function useUnreadCount(enabled = true) {
  return useQuery({
    queryKey: [...notificationKeys.all, 'unread'],
    queryFn: async () => (await api.get<{ unread: number }>('/notifications/unread-count')).data.unread,
    enabled,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });
}

export function useNotifications(page: number, size: number, unreadOnly: boolean) {
  return useQuery({
    queryKey: [...notificationKeys.all, 'list', page, size, unreadOnly],
    queryFn: async () =>
      (await api.get<Page<NotificationItem>>('/notifications', { params: { page, size, unread_only: unreadOnly } })).data,
  });
}

export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}

export function useMarkAllRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/notifications/read-all'),
    onSuccess: () => qc.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}
