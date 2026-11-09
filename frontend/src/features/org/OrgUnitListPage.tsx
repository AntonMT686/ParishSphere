import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import type { OrgUnit } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, PageHeader, StatusBadge } from '@/design-system';
import { NotFoundPage } from '@/features/NotFoundPage';
import { fetchUnits, useOrgTypes } from './api';
import { OrgUnitDialog } from './OrgUnitDialog';

export function OrgUnitListPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { typeCode = '' } = useParams();
  const { data: types, isLoading } = useOrgTypes();
  const type = types?.find((x) => x.code.toLowerCase() === typeCode.toLowerCase());
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('ACTIVE');
  const [creating, setCreating] = useState(false);
  const deferredQ = useDeferredValue(q);
  if (isLoading) return null;
  if (!type) return <NotFoundPage />;
  const ta = i18n.language === 'ta';
  const title = ta && type.name_local ? type.name_local : type.name_plural;

  const columns: GridColDef<OrgUnit>[] = [
    { field: 'code', headerName: t('org.code'), width: 120 },
    {
      field: 'name', headerName: t('common.name'), flex: 1.2, minWidth: 200,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600}>{row.name}</Typography>
          {row.name_local && <Typography variant="caption" color="text.secondary">{row.name_local}</Typography>}
        </Stack>
      ),
    },
    { field: 'parent', headerName: t('org.parent'), flex: 0.8, minWidth: 140, sortable: false, valueGetter: (_v, row) => row.parent?.name ?? '' },
    {
      field: 'office_bearers', headerName: t('org.officeBearers'), flex: 1.6, minWidth: 260, sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: '100%', overflow: 'hidden' }}>
          {row.office_bearers.filter((b) => b.grants_role).map((b) => (
            <Chip key={b.id} size="small" variant="outlined" label={`${b.position_name}: ${b.holder_name}`} />
          ))}
        </Stack>
      ),
    },
    { field: 'status', headerName: t('common.status'), width: 120, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];

  return (
    <>
      <PageHeader
        title={title}
        subtitle={type.description ?? undefined}
        breadcrumbs={[{ label: t('nav.organisations') }, { label: title }]}
        actions={
          <PermissionGate anyOf="org_unit.create">
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreating(true)}
              disabled={!type.allow_multiple_units && type.unit_count > 0}>
              {t('org.newUnit', { type: type.name })}
            </Button>
          </PermissionGate>
        }
      />
      <DataTable<OrgUnit>
        queryKey={['org', 'units', 'list', type.code, deferredQ, status]}
        fetchPage={(req) => fetchUnits(req, { type: type.code, q: deferredQ.trim(), status })}
        columns={columns}
        onRowClick={(u) => navigate(`/org/units/${u.id}`)}
        initialSort={[{ field: 'name', sort: 'asc' }]}
        emptyTitle={t('org.emptyTitle', { type: type.name_plural })}
        toolbar={
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { sm: 320 } }} />
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160, maxWidth: { sm: 200 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              <MenuItem value="ACTIVE">{t('common.active')}</MenuItem>
              <MenuItem value="INACTIVE">{t('common.inactive')}</MenuItem>
            </TextField>
          </Stack>
        }
      />
      <OrgUnitDialog open={creating} onClose={() => setCreating(false)} type={type}
        onSaved={(u) => navigate(`/org/units/${u.id}`)} />
    </>
  );
}
