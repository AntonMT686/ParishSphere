import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Member } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { fetchMembers } from './api';
import { useLabels } from './labels';
import { MemberDrawer } from './MemberDrawer';

export function MembersPage() {
  const { t } = useTranslation();
  const L = useLabels();
  const [q, setQ] = useState('');
  const [gender, setGender] = useState('');
  const [status, setStatus] = useState('ACTIVE');
  const [ageMin, setAgeMin] = useState('');
  const [ageMax, setAgeMax] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const deferredQ = useDeferredValue(q);
  const filters = { q: deferredQ.trim(), gender, status, age_min: ageMin === '' ? '' as const : Number(ageMin), age_max: ageMax === '' ? '' as const : Number(ageMax) };
  const columns: GridColDef<Member>[] = [
    { field: 'code', headerName: t('people.memberId'), width: 120 },
    {
      field: 'first_name', headerName: t('common.name'), flex: 1.2, minWidth: 200,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600}>{row.full_name}</Typography>
          {row.name_local && <Typography variant="caption" color="text.secondary">{row.name_local}</Typography>}
        </Stack>
      ),
    },
    { field: 'family', headerName: t('people.family'), flex: 1, minWidth: 160, valueGetter: (_v, r) => r.family.name },
    { field: 'anbiyam', headerName: t('nav.anbiyam'), flex: 1, minWidth: 150, sortable: false, valueGetter: (_v, r) => r.anbiyam?.name ?? '—' },
    { field: 'relationship_to_head', headerName: t('people.relationship'), width: 140, sortable: false, valueFormatter: (v: string) => L.rel(v) },
    { field: 'gender', headerName: t('people.genderLabel'), width: 100, sortable: false, valueFormatter: (v: string) => L.gender(v) },
    { field: 'age', headerName: t('people.age'), width: 80, sortable: false, align: 'right', headerAlign: 'right' },
    { field: 'status', headerName: t('common.status'), width: 140, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.members')}
        subtitle={t('people.membersSubtitle')}
        breadcrumbs={[{ label: t('nav.people') }, { label: t('nav.members') }]}
        actions={<PermissionGate anyOf="member.export"><ExportMenu url="/members/export" params={{ q: filters.q, gender, status }} filename="member-register" /></PermissionGate>}
      />
      <DataTable<Member>
        queryKey={['members', 'list', filters]}
        fetchPage={(req) => fetchMembers(req, filters)}
        columns={columns}
        onRowClick={(m) => setSelected(m.id)}
        initialSort={[{ field: 'first_name', sort: 'asc' }]}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField label={t('people.searchMembers')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 320 } }} />
            <TextField select label={t('people.genderLabel')} value={gender} onChange={(e) => setGender(e.target.value)} sx={{ minWidth: 130, maxWidth: { md: 150 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {['M', 'F', 'O'].map((g) => <MenuItem key={g} value={g}>{L.gender(g)}</MenuItem>)}
            </TextField>
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 160, maxWidth: { md: 190 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {['ACTIVE', 'INACTIVE', 'DECEASED', 'TRANSFERRED_OUT'].map((s) => <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
            </TextField>
            <TextField label={t('people.ageFrom')} type="number" value={ageMin} onChange={(e) => setAgeMin(e.target.value)} sx={{ maxWidth: { md: 110 } }} />
            <TextField label={t('people.ageTo')} type="number" value={ageMax} onChange={(e) => setAgeMax(e.target.value)} sx={{ maxWidth: { md: 110 } }} />
          </Stack>
        }
      />
      <MemberDrawer memberId={selected} onClose={() => setSelected(null)} />
    </>
  );
}
