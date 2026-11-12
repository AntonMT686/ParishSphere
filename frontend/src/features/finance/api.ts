import { useQuery } from '@tanstack/react-query';
import { api, type Page } from '@/api/client';
import type { FinAccount, FinCategory, FinPeriod, FinPeriodListItem, FinSummary, FinTxn, FinTxnListItem } from '@/api/types';
import { useCan } from '@/auth/authStore';
import type { PageRequest } from '@/design-system';

export const finKeys = {
  all: ['finance'] as const,
  accounts: ['finance', 'accounts'] as const,
  categories: ['finance', 'categories'] as const,
  txns: ['finance', 'transactions'] as const,
  periods: ['finance', 'periods'] as const,
  summary: ['finance', 'summary'] as const,
};

const clean = (o: object) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== undefined && v !== null));

export const KINDS = ['INCOME', 'EXPENSE', 'TRANSFER'] as const;
export const METHODS = ['CASH', 'CHEQUE', 'BANK_TRANSFER', 'UPI', 'CARD', 'ONLINE'] as const;
export const TXN_STATUSES = ['PENDING', 'DRAFT', 'IN_REVIEW', 'REWORK', 'APPROVED', 'REJECTED'] as const;

export function useAccounts(includeInactive = false) {
  return useQuery({
    queryKey: [...finKeys.accounts, includeInactive],
    queryFn: async () => (await api.get<FinAccount[]>('/finance/accounts', { params: includeInactive ? { include_inactive: true } : {} })).data,
  });
}
export function useCategories(includeInactive = false) {
  return useQuery({
    queryKey: [...finKeys.categories, includeInactive],
    queryFn: async () => (await api.get<FinCategory[]>('/finance/categories', { params: includeInactive ? { include_inactive: true } : {} })).data,
    staleTime: 5 * 60_000,
  });
}
export interface TxnFilters { q?: string; kind?: string; status?: string; category?: string; account?: string; org_unit?: string; period?: string; date_from?: string; date_to?: string }
export async function fetchTxns(req: PageRequest, f: TxnFilters): Promise<Page<FinTxnListItem>> {
  return (await api.get<Page<FinTxnListItem>>('/finance/transactions', { params: clean({ ...req, ...f }) })).data;
}
export function useTxn(id: string | undefined) {
  return useQuery({
    queryKey: [...finKeys.txns, id],
    queryFn: async () => (await api.get<FinTxn>(`/finance/transactions/${id}`)).data,
    enabled: Boolean(id),
  });
}
export function usePeriods() {
  return useQuery({ queryKey: finKeys.periods, queryFn: async () => (await api.get<FinPeriodListItem[]>('/finance/periods')).data });
}
export function usePeriod(key: string) {
  return useQuery({ queryKey: [...finKeys.periods, key], queryFn: async () => (await api.get<FinPeriod>(`/finance/periods/${key}`)).data });
}
export function useFinSummary() {
  const can = useCan();
  return useQuery({
    queryKey: finKeys.summary,
    queryFn: async () => (await api.get<FinSummary>('/finance/summary')).data,
    enabled: can(['finance.view_summary', 'finance.view']),
  });
}

/** ₹ with Indian digit grouping. */
export function inr(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(Number(v));
}

/** Download a protected file through the API and hand it to the browser. */
export async function downloadBlob(url: string, filename: string) {
  const res = await api.get(url, { responseType: 'blob' });
  const href = URL.createObjectURL(res.data as Blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
