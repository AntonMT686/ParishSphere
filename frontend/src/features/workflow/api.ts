import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type {
  WorkflowDefinition,
  WorkflowDelegation,
  WorkflowEntityType,
  WorkflowInstance,
  WorkflowInstanceSummary,
  WorkflowTaskItem,
} from '@/api/types';
import { useCan } from '@/auth/authStore';
import type { PageRequest } from '@/design-system';

export const wfKeys = {
  all: ['workflow'] as const,
  tasks: ['workflow', 'tasks'] as const,
  summary: ['workflow', 'tasks', 'summary'] as const,
  instances: ['workflow', 'instances'] as const,
  definitions: ['workflow', 'definitions'] as const,
  delegations: ['workflow', 'delegations'] as const,
};

const clean = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null));

export interface TaskFilters { state: 'PENDING' | 'DONE'; entity_type?: string; overdue?: boolean }
export async function fetchTasks(req: PageRequest, f: TaskFilters): Promise<Page<WorkflowTaskItem>> {
  return (await api.get<Page<WorkflowTaskItem>>('/workflow/tasks', { params: clean({ ...req, ...f }) })).data;
}

export interface InstanceFilters { status?: string; entity_type?: string; q?: string; mine?: boolean }
export async function fetchInstances(req: PageRequest, f: InstanceFilters): Promise<Page<WorkflowInstanceSummary>> {
  return (await api.get<Page<WorkflowInstanceSummary>>('/workflow/instances', { params: clean({ ...req, ...f }) })).data;
}

export function useTaskSummary() {
  return useQuery({
    queryKey: wfKeys.summary,
    queryFn: async () => (await api.get<{ pending: number; overdue: number }>('/workflow/tasks/summary')).data,
    refetchInterval: 120_000,
  });
}

export function useInstance(id: string) {
  return useQuery({
    queryKey: [...wfKeys.instances, id],
    queryFn: async () => (await api.get<WorkflowInstance>(`/workflow/instances/${id}`)).data,
  });
}

/** Every approval run of one record, newest first (used by module pages from T11 on). */
export function useEntityApprovals(entityType: string, entityId: string | undefined) {
  return useQuery({
    queryKey: [...wfKeys.instances, 'entity', entityType, entityId],
    queryFn: async () => (await api.get<WorkflowInstance[]>(`/workflow/entities/${entityType}/${entityId}`)).data,
    enabled: Boolean(entityId),
  });
}

export function useEntityTypes() {
  const can = useCan();
  return useQuery({
    queryKey: [...wfKeys.definitions, 'types'],
    queryFn: async () => (await api.get<WorkflowEntityType[]>('/workflow/entity-types')).data,
    enabled: can('workflow.view'),
    staleTime: 5 * 60_000,
  });
}

export function useDefinitions(code?: string) {
  return useQuery({
    queryKey: [...wfKeys.definitions, 'list', code ?? ''],
    queryFn: async () => (await api.get<WorkflowDefinition[]>('/workflow/definitions', { params: clean({ code }) })).data,
  });
}

export function useDefinition(id: string | undefined) {
  return useQuery({
    queryKey: [...wfKeys.definitions, id],
    queryFn: async () => (await api.get<WorkflowDefinition>(`/workflow/definitions/${id}`)).data,
    enabled: Boolean(id),
  });
}

export function useDelegations(all = false, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...wfKeys.delegations, all],
    queryFn: async () => (await api.get<WorkflowDelegation[]>('/workflow/delegations', { params: all ? { all: true } : {} })).data,
  });
}

/** English fallback labels; the UI translates through i18n keys `workflow.entity.<CODE>`. */
export const ENTITY_TYPE_CODES = ['ACTIVITY', 'MEETING_MINUTES', 'FIN_TRANSACTION', 'FIN_PERIOD', 'NOTICE'] as const;
