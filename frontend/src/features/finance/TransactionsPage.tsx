import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { FinTxnListItem } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { OrgUnitSelect } from '@/features/activities/shared';
import { formatDate } from '@/lib/format';
import { fetchTxns, finKeys, inr, KINDS, TXN_STATUSES, useAccounts, useCategories } from './api';
import { FinanceCards } from './FinanceCards';
import { TransactionDialog } from './TransactionDialog';

export function Amount({ kind, amount }: { kind: string; amount: string | number }) {
  const n = Number(amount);
  // Money in is green and "+", money out red and "−"; a negative correction of income reduces income.
  const into = kind === 'INCOME' ? n > 0 : kind === 'EXPENSE' ? n < 0 : null;
  const color = into === null ? 'text.primary' : into ? 'success.main' : 'error.main';
  const sign = into === null ? '⇄ ' : into ? '+' : '−';
  return <Typography component="span" variant="body2" fontWeight={600} color={color} sx={{ fontVariantNumeric: 'tabular-nums' }}>{sign}{inr(Math.abs(n))}</Typography>;
}

export function TransactionsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: accounts = [] } = useAccounts();
  const { data: categories = [] } = useCategories();
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('');
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [params] = useSearchParams();
  const [account, setAccount] = useState(params.get('account') ?? '');
  const [unit, setUnit] = useState('ALL');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [adding, setAdding] = useState(false);
  const filters = {
    q: useDeferredValue(q).trim(), kind, status, category, account, date_from: from, date_to: to,
    org_unit: unit === 'ALL' ? undefined : unit === '' ? 'PARISH' : unit,
  };
  const columns: GridColDef<FinTxnListItem>[] = [
    { field: 'txn_date', headerName: t('finance.date'), width: 115, valueFormatter: (v: string) => formatDate(v) },
    {
      field: 'description', headerName: t('finance.particulars'), flex: 1.6, minWidth: 240, sortable: false,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.description}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {row.code} · {row.category?.name ?? t('finance.kind.TRANSFER')}{row.payer_payee ? ` · ${row.payer_payee}` : ''}{row.is_correction ? ` · ${t('finance.correction')}` : ''}
          </Typography>
        </Stack>
      ),
    },
    { field: 'org_unit', headerName: t('activities.organisation'), flex: 0.9, minWidth: 140, sortable: false, valueGetter: (_v, r) => r.org_unit?.name ?? t('activities.parishLevel') },
    { field: 'account', headerName: t('finance.account'), width: 150, sortable: false, valueGetter: (_v, r) => (r.to_account ? `${r.account.name} → ${r.to_account.name}` : r.account.name) },
    { field: 'amount', headerName: t('finance.amount'), width: 150, align: 'right', headerAlign: 'right', renderCell: ({ row }) => <Amount kind={row.kind} amount={row.amount} /> },
    { field: 'status', headerName: t('common.status'), width: 130, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.transactions')}
        subtitle={t('finance.subtitle')}
        breadcrumbs={[{ label: t('nav.finance') }, { label: t('nav.transactions') }]}
        actions={
          <Stack direction="row" spacing={1}>
            <PermissionGate anyOf="finance.export"><ExportMenu url="/finance/transactions/export" params={filters} filename="transactions" /></PermissionGate>
            <PermissionGate anyOf="finance.create"><Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('finance.newEntry')}</Button></PermissionGate>
          </Stack>
        }
      />
      <FinanceCards />
      <DataTable<FinTxnListItem>
        queryKey={[...finKeys.txns, 'list', filters]}
        fetchPage={(req) => fetchTxns(req, filters)}
        columns={columns}
        onRowClick={(x) => navigate(`/finance/transactions/${x.id}`)}
        initialSort={[{ field: 'txn_date', sort: 'desc' }]}
        emptyTitle={t('finance.none')}
        toolbar={
          <Stack spacing={1.5}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 240 } }} />
              <TextField select label={t('finance.kindLabel')} value={kind} onChange={(e) => { setKind(e.target.value); setCategory(''); }} sx={{ maxWidth: { md: 160 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {KINDS.map((k) => <MenuItem key={k} value={k}>{t(`finance.kind.${k}`)}</MenuItem>)}
              </TextField>
              <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ maxWidth: { md: 180 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {TXN_STATUSES.map((s) => <MenuItem key={s} value={s}>{s === 'PENDING' ? t('finance.undecided') : t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
              </TextField>
              <TextField select label={t('finance.category')} value={category} onChange={(e) => setCategory(e.target.value)} sx={{ maxWidth: { md: 220 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {categories.filter((c) => !kind || c.kind === kind).map((c) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <OrgUnitSelect permission="finance.view" allowAll value={unit} onChange={setUnit} sx={{ maxWidth: { md: 240 } }} />
              <TextField select label={t('finance.account')} value={account} onChange={(e) => setAccount(e.target.value)} sx={{ maxWidth: { md: 200 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {accounts.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}</MenuItem>)}
              </TextField>
              <TextField type="date" label={t('activities.from')} value={from} onChange={(e) => setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ maxWidth: { md: 170 } }} />
              <TextField type="date" label={t('activities.to')} value={to} onChange={(e) => setTo(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ maxWidth: { md: 170 } }} />
            </Stack>
          </Stack>
        }
      />
      <TransactionDialog open={adding} onClose={() => setAdding(false)} />
    </>
  );
}
