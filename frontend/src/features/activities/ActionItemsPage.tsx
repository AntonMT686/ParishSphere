import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import type { ActionItem } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader } from '@/design-system';
import { formatDate } from '@/lib/format';
import { ActionItemDrawer, ActionStatus, ActionStatusSelect, NewActionDialog } from './ActionItems';
import { actKeys, fetchActions, useActionSummary } from './api';
import { OrgUnitSelect } from './shared';

export function ActionItemsPage() {
  const { t } = useTranslation();
  const can = useCan();
  const [params, setParams] = useSearchParams();
  const canSeeAll = can('action_item.view');
  const [tab, setTab] = useState<'mine' | 'all'>('mine');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('ACTIVE');
  const [overdue, setOverdue] = useState(false);
  const [unit, setUnit] = useState('ALL');
  const [adding, setAdding] = useState(false);
  const { data: summary } = useActionSummary();
  const open = params.get('open');
  const filters = {
    q: useDeferredValue(q).trim(), status, overdue, mine: tab === 'mine',
    org_unit: tab === 'all' && unit !== 'ALL' ? (unit === '' ? 'PARISH' : unit) : undefined,
  };
  const columns: GridColDef<ActionItem>[] = [
    {
      field: 'title', headerName: t('actions.item'), flex: 1.6, minWidth: 240,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {row.code}{row.source.title ? ` · ${row.source.title}` : ''}{row.org_unit ? ` · ${row.org_unit.name}` : ''}
          </Typography>
        </Stack>
      ),
    },
    { field: 'owner', headerName: t('actions.responsible'), width: 170, sortable: false, valueGetter: (_v, r) => r.owner?.name ?? r.owner_name ?? '—' },
    { field: 'due_date', headerName: t('actions.due'), width: 130,
      renderCell: ({ row }) => <Typography variant="body2" color={row.overdue ? 'error' : undefined} sx={{ lineHeight: '52px' }}>{row.due_date ? formatDate(row.due_date) : '—'}</Typography> },
    { field: 'progress_pct', headerName: t('actions.progress'), width: 130, sortable: false,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%' }}>
          <LinearProgress variant="determinate" value={row.progress_pct} sx={{ height: 6, borderRadius: 3 }} aria-label={`${row.progress_pct}%`} />
        </Stack>
      ) },
    { field: 'status', headerName: t('common.status'), width: 130, sortable: false, renderCell: ({ row }) => <ActionStatus item={row} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.actionItems')}
        subtitle={summary ? t('actions.subtitle', { open: summary.open, overdue: summary.overdue }) : undefined}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.actionItems') }]}
        actions={
          <Stack direction="row" spacing={1}>
            {canSeeAll && tab === 'all' && <ExportMenu url="/action-items/export" params={{ ...filters, mine: undefined }} filename="action-items" />}
            <PermissionGate anyOf="action_item.create">
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('actions.new')}</Button>
            </PermissionGate>
          </Stack>
        }
      />
      {canSeeAll && (
        <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab value="mine" label={t('actions.mine')} />
          <Tab value="all" label={t('actions.all')} />
        </Tabs>
      )}
      <DataTable<ActionItem>
        queryKey={[...actKeys.actions, 'table', filters]}
        fetchPage={(req) => fetchActions(req, filters)}
        columns={columns}
        onRowClick={(a) => setParams({ open: a.id })}
        initialSort={[{ field: 'due_date', sort: 'asc' }]}
        emptyTitle={tab === 'mine' ? t('actions.noneMine') : t('actions.none')}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
            <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 260 } }} />
            <ActionStatusSelect value={status} onChange={setStatus} />
            {tab === 'all' && <OrgUnitSelect permission="action_item.view" allowAll value={unit} onChange={setUnit} sx={{ maxWidth: { md: 260 } }} />}
            <FormControlLabel control={<Switch checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />} label={t('actions.overdueOnly')} />
          </Stack>
        }
      />
      <NewActionDialog open={adding} onClose={() => setAdding(false)} />
      <ActionItemDrawer id={open} onClose={() => setParams({})} />
    </>
  );
}
