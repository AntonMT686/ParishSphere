import AddIcon from '@mui/icons-material/GroupAddOutlined';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import type { FamilyListItem } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { OrgUnitPicker } from '@/features/org/pickers';
import { formatDate } from '@/lib/format';
import { fetchFamilies } from './api';

export function FamiliesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [anbiyam, setAnbiyam] = useState<{ id: string; name: string; code: string } | null>(null);
  const deferredQ = useDeferredValue(q);
  const filters = { q: deferredQ.trim(), status, anbiyam: anbiyam?.id };
  const columns: GridColDef<FamilyListItem>[] = [
    { field: 'code', headerName: t('people.familyId'), width: 120 },
    {
      field: 'family_name', headerName: t('people.family'), flex: 1.2, minWidth: 200,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600}>{row.family_name}</Typography>
          {row.family_name_local && <Typography variant="caption" color="text.secondary">{row.family_name_local}</Typography>}
        </Stack>
      ),
    },
    { field: 'head_name', headerName: t('people.head'), flex: 1, minWidth: 150, sortable: false },
    { field: 'anbiyam', headerName: t('nav.anbiyam'), flex: 1, minWidth: 150, sortable: false, valueGetter: (_v, r) => r.anbiyam?.name ?? '—' },
    { field: 'member_count', headerName: t('nav.members'), width: 100, sortable: false, align: 'right', headerAlign: 'right' },
    { field: 'phone', headerName: t('common.phone'), width: 150, sortable: false },
    { field: 'status', headerName: t('common.status'), width: 160, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
    { field: 'registered_on', headerName: t('people.registered'), width: 130, valueFormatter: (v: string) => formatDate(v) },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.families')}
        subtitle={t('people.familiesSubtitle')}
        breadcrumbs={[{ label: t('nav.people') }, { label: t('nav.families') }]}
        actions={
          <>
            <PermissionGate anyOf="family.export">
              <ExportMenu url="/families/export" params={filters} filename="family-register" />
            </PermissionGate>
            <PermissionGate anyOf="family.create">
              <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/families/new">{t('people.register')}</Button>
            </PermissionGate>
          </>
        }
      />
      <DataTable<FamilyListItem>
        queryKey={['families', 'list', filters]}
        fetchPage={(req) => fetchFamilies(req, filters)}
        columns={columns}
        onRowClick={(f) => navigate(`/families/${f.id}`)}
        initialSort={[{ field: 'family_name', sort: 'asc' }]}
        emptyTitle={t('people.noFamilies')}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField label={t('people.searchFamilies')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 360 } }} />
            <OrgUnitPicker label={t('nav.anbiyam')} type="ANBIYAM" value={anbiyam} onChange={setAnbiyam} />
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 200, maxWidth: { md: 240 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {['ACTIVE', 'PENDING_ANBIYAM', 'INACTIVE', 'TRANSFERRED_OUT', 'MERGED'].map((s) => (
                <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>
              ))}
            </TextField>
          </Stack>
        }
      />
    </>
  );
}
