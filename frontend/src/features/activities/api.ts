import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type {
  ActionItem, Activity, ActivityListItem, AttachmentItem, Attendance, CalendarEvent, Meeting, MeetingListItem, ScopedUnit,
} from '@/api/types';
import type { PageRequest } from '@/design-system';

export const actKeys = {
  activities: ['activities'] as const,
  meetings: ['meetings'] as const,
  actions: ['action-items'] as const,
  calendar: ['calendar'] as const,
  files: ['attachments'] as const,
};

const clean = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null && v !== false));

export const CATEGORIES = ['SPIRITUAL', 'LITURGICAL', 'CHARITY', 'SOCIAL', 'CULTURAL', 'EDUCATIONAL', 'YOUTH', 'FAMILY', 'OTHER'] as const;
export const ACTIVITY_STATUSES = ['DRAFT', 'IN_REVIEW', 'REWORK', 'APPROVED', 'COMPLETED', 'REJECTED', 'CANCELLED'] as const;
export const MEETING_TYPES = ['REGULAR', 'SPECIAL', 'GENERAL_BODY', 'EMERGENCY'] as const;

export interface ActivityFilters { q?: string; org_unit?: string; status?: string; category?: string; date_from?: string; date_to?: string; mine?: boolean }
export async function fetchActivities(req: PageRequest, f: ActivityFilters): Promise<Page<ActivityListItem>> {
  return (await api.get<Page<ActivityListItem>>('/activities', { params: clean({ ...req, ...f }) })).data;
}
export function useActivity(id: string | undefined) {
  return useQuery({
    queryKey: [...actKeys.activities, id],
    queryFn: async () => (await api.get<Activity>(`/activities/${id}`)).data,
    enabled: Boolean(id),
  });
}

export interface MeetingFilters { q?: string; org_unit?: string; status?: string; when?: 'upcoming' | 'past' }
export async function fetchMeetings(req: PageRequest, f: MeetingFilters): Promise<Page<MeetingListItem>> {
  return (await api.get<Page<MeetingListItem>>('/meetings', { params: clean({ ...req, ...f }) })).data;
}
export function useMeeting(id: string | undefined) {
  return useQuery({
    queryKey: [...actKeys.meetings, id],
    queryFn: async () => (await api.get<Meeting>(`/meetings/${id}`)).data,
    enabled: Boolean(id),
  });
}
export function useAttendance(id: string) {
  return useQuery({
    queryKey: [...actKeys.meetings, id, 'attendance'],
    queryFn: async () => (await api.get<Attendance>(`/meetings/${id}/attendance`)).data,
  });
}

export interface ActionFilters { q?: string; status?: string; mine?: boolean; overdue?: boolean; org_unit?: string; meeting?: string; activity?: string }
export async function fetchActions(req: PageRequest, f: ActionFilters): Promise<Page<ActionItem>> {
  return (await api.get<Page<ActionItem>>('/action-items', { params: clean({ ...req, ...f }) })).data;
}
export function useActionItems(f: ActionFilters, enabled = true) {
  return useQuery({
    queryKey: [...actKeys.actions, 'list', f],
    queryFn: () => fetchActions({ page: 1, size: 50 }, f),
    enabled,
  });
}
export function useActionItem(id: string | null) {
  return useQuery({
    queryKey: [...actKeys.actions, id],
    queryFn: async () => (await api.get<ActionItem>(`/action-items/${id}`)).data,
    enabled: Boolean(id),
  });
}
export function useActionSummary() {
  return useQuery({
    queryKey: [...actKeys.actions, 'summary'],
    queryFn: async () => (await api.get<{ open: number; overdue: number }>('/action-items/summary')).data,
  });
}

export function useCalendar(start: string, end: string, orgUnit?: string) {
  return useQuery({
    queryKey: [...actKeys.calendar, start, end, orgUnit ?? ''],
    queryFn: async () => (await api.get<CalendarEvent[]>('/calendar', { params: clean({ start, end, org_unit: orgUnit }) })).data,
  });
}

/** `files` base path, e.g. `/activities/{id}` or `/meetings/{id}`. */
export function useAttachments(base: string) {
  return useQuery({
    queryKey: [...actKeys.files, base],
    queryFn: async () => (await api.get<AttachmentItem[]>(`${base}/attachments`)).data,
  });
}

/** Organisations the user may act for with `permission` (+ whether parish-level records are allowed). */
export function useMyUnits(permission: string, enabled = true) {
  return useQuery({
    queryKey: ['org', 'mine', permission],
    queryFn: async () => (await api.get<{ parish: boolean; units: ScopedUnit[] }>('/org-units/mine', { params: { permission } })).data,
    enabled,
    staleTime: 60_000,
  });
}

/** Local date-time string for `<input type="datetime-local">` from an API value (wall time, no zone). */
export const toLocalInput = (v: string | null | undefined) => (v ? v.slice(0, 16) : '');
export const today = () => new Date().toISOString().slice(0, 10);
