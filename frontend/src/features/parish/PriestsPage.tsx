import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { Priest } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, PageHeader, StatusBadge } from '@/design-system';
import { fetchPriests, PRIEST_STATUSES } from './api';
import { PriestDialog } from './PriestDialog';

export function PriestsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [serving, setServing] = useState(false);
  const [adding, setAdding] = useState(false);
  const filters = { q: useDeferredValue(q).trim(), status, serving: serving || undefined };
  const columns: GridColDef<Priest>[] = [
    {
      field: 'full_name', headerName: t('common.name'), flex: 1.3, minWidth: 220,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600}>{row.display_name}</Typography>
          {row.name_local && <Typography variant="caption" color="text.secondary">{row.name_local}</Typography>}
        </Stack>
      ),
    },
    {
      field: 'current_roles', headerName: t('priests.serving'), flex: 1, minWidth: 200, sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: '100%' }}>
          {row.current_roles.length ? row.current_roles.map((r) => <Chip key={r} size="small" color="primary" variant="outlined" label={t(`priests.role.${r}`)} />) : '—'}
        </Stack>
      ),
    },
    { field: 'clergy_type', headerName: t('priests.clergyType'), width: 140, sortable: false,
      valueGetter: (_v, r) => r.clergy_type === 'RELIGIOUS' ? (r.congregation ?? t('priests.clergy.RELIGIOUS')) : (r.home_diocese ?? t('priests.clergy.DIOCESAN')) },
    { field: 'phone', headerName: t('common.phone'), width: 140, sortable: false },
    { field: 'status', headerName: t('common.status'), width: 120, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.priests')}
        subtitle={t('priests.subtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.priests') }]}
        actions={<PermissionGate anyOf="priest.create"><Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('priests.add')}</Button></PermissionGate>}
      />
      <DataTable<Priest>
        queryKey={['priests', 'list', filters]}
        fetchPage={(req) => fetchPriests(req, filters)}
        columns={columns}
        onRowClick={(p) => navigate(`/admin/priests/${p.id}`)}
        initialSort={[{ field: 'full_name', sort: 'asc' }]}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
            <TextField label={t('priests.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 320 } }} />
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 150, maxWidth: { md: 180 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {PRIEST_STATUSES.map((s) => <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
            </TextField>
            <FormControlLabel control={<Switch checked={serving} onChange={(e) => setServing(e.target.checked)} />} label={t('priests.servingOnly')} />
          </Stack>
        }
      />
      <PriestDialog open={adding} onClose={() => setAdding(false)} onCreated={(p) => navigate(`/admin/priests/${p.id}`)} />
    </>
  );
}
