import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import type { ActivityListItem } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { formatDate, formatMoney } from '@/lib/format';
import { ACTIVITY_STATUSES, actKeys, CATEGORIES, fetchActivities } from './api';
import { OrgUnitSelect } from './shared';

export function ActivitiesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [unit, setUnit] = useState('ALL');
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [mine, setMine] = useState(false);
  const filters = {
    q: useDeferredValue(q).trim(), org_unit: unit === 'ALL' ? undefined : unit === '' ? 'PARISH' : unit,
    status, category, date_from: from, date_to: to, mine,
  };
  const columns: GridColDef<ActivityListItem>[] = [
    { field: 'activity_date', headerName: t('activities.date'), width: 120, valueFormatter: (v: string) => formatDate(v) },
    {
      field: 'title', headerName: t('activities.activity'), flex: 1.6, minWidth: 240,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {row.code}{row.category ? ` · ${t(`activities.category.${row.category}`)}` : ''}{row.location ? ` · ${row.location}` : ''}
          </Typography>
        </Stack>
      ),
    },
    { field: 'org_unit', headerName: t('activities.organisation'), flex: 1, minWidth: 160, sortable: false,
      valueGetter: (_v, r) => r.org_unit?.name ?? t('activities.parishLevel') },
    { field: 'responsible', headerName: t('activities.responsible'), width: 160, sortable: false, valueFormatter: (v: string | null) => v ?? '—' },
    { field: 'planned_amount', headerName: t('activities.amount'), width: 120, sortable: false, align: 'right', headerAlign: 'right',
      valueGetter: (_v, r) => r.actual_amount ?? r.planned_amount, valueFormatter: (v: string | null) => (v == null ? '—' : formatMoney(v)) },
    { field: 'status', headerName: t('common.status'), width: 130, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.activityList')}
        subtitle={t('activities.subtitle')}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.activityList') }]}
        actions={
          <Stack direction="row" spacing={1}>
            <PermissionGate anyOf="activity.export">
              <ExportMenu url="/activities/export" params={{ ...filters, mine: undefined }} filename="activities" />
            </PermissionGate>
            <PermissionGate anyOf="activity.create">
              <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/activities/new">{t('activities.new')}</Button>
            </PermissionGate>
          </Stack>
        }
      />
      <DataTable<ActivityListItem>
        queryKey={[...actKeys.activities, 'list', filters]}
        fetchPage={(req) => fetchActivities(req, filters)}
        columns={columns}
        onRowClick={(a) => navigate(`/activities/${a.id}`)}
        initialSort={[{ field: 'activity_date', sort: 'desc' }]}
        emptyTitle={t('activities.none')}
        toolbar={
          <Stack spacing={1.5}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 260 } }} />
              <OrgUnitSelect permission="activity.view" allowAll value={unit} onChange={setUnit} sx={{ maxWidth: { md: 260 } }} />
              <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ maxWidth: { md: 180 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {ACTIVITY_STATUSES.map((s) => <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
              </TextField>
              <TextField select label={t('activities.categoryLabel')} value={category} onChange={(e) => setCategory(e.target.value)} sx={{ maxWidth: { md: 180 } }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                {CATEGORIES.map((c) => <MenuItem key={c} value={c}>{t(`activities.category.${c}`)}</MenuItem>)}
              </TextField>
            </Stack>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
              <TextField type="date" label={t('activities.from')} value={from} onChange={(e) => setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ maxWidth: { md: 180 } }} />
              <TextField type="date" label={t('activities.to')} value={to} onChange={(e) => setTo(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} sx={{ maxWidth: { md: 180 } }} />
              <FormControlLabel control={<Switch checked={mine} onChange={(e) => setMine(e.target.checked)} />} label={t('activities.recordedByMe')} />
            </Stack>
          </Stack>
        }
      />
    </>
  );
}
