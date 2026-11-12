import AddIcon from '@mui/icons-material/Add';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { MeetingListItem } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { formatWallTime } from '@/lib/format';
import { actKeys, fetchMeetings } from './api';
import { MeetingDialog } from './MeetingDialog';
import { OrgUnitSelect } from './shared';

export function MeetingsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [tab, setTab] = useState<'upcoming' | 'past' | 'all'>('upcoming');
  const [q, setQ] = useState('');
  const [unit, setUnit] = useState('ALL');
  const [status, setStatus] = useState('');
  const [scheduling, setScheduling] = useState(false);
  const filters = {
    q: useDeferredValue(q).trim(), org_unit: unit === 'ALL' ? undefined : unit === '' ? 'PARISH' : unit, status,
    when: tab === 'all' ? undefined : tab,
  };
  const columns: GridColDef<MeetingListItem>[] = [
    { field: 'scheduled_at', headerName: t('meetings.when'), width: 190, valueFormatter: (v: string) => formatWallTime(v) },
    {
      field: 'title', headerName: t('meetings.meeting'), flex: 1.5, minWidth: 220,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>{row.code}{row.location ? ` · ${row.location}` : ''}</Typography>
        </Stack>
      ),
    },
    { field: 'org_unit', headerName: t('activities.organisation'), flex: 1, minWidth: 160, sortable: false, valueGetter: (_v, r) => r.org_unit?.name ?? t('activities.parishLevel') },
    { field: 'status', headerName: t('common.status'), width: 120, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
    {
      field: 'minutes_status', headerName: t('meetings.minutes'), width: 170, sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: '100%' }}>
          {row.minutes_status ? <StatusBadge status={row.minutes_status} /> : <Typography variant="caption" color="text.secondary">—</Typography>}
          {row.open_actions > 0 && <Chip size="small" variant="outlined" label={t('meetings.openActions', { count: row.open_actions })} />}
        </Stack>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.meetings')}
        subtitle={t('meetings.subtitle')}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.meetings') }]}
        actions={
          <Stack direction="row" spacing={1}>
            <PermissionGate anyOf="meeting.export"><ExportMenu url="/meetings/export" params={{ ...filters, when: undefined }} filename="meetings" /></PermissionGate>
            <PermissionGate anyOf="meeting.create">
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setScheduling(true)}>{t('meetings.schedule')}</Button>
            </PermissionGate>
          </Stack>
        }
      />
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="upcoming" label={t('meetings.upcoming')} />
        <Tab value="past" label={t('meetings.past')} />
        <Tab value="all" label={t('common.all')} />
      </Tabs>
      <DataTable<MeetingListItem>
        queryKey={[...actKeys.meetings, 'list', filters]}
        fetchPage={(req) => fetchMeetings(req, filters)}
        columns={columns}
        onRowClick={(m) => navigate(`/meetings/${m.id}`)}
        initialSort={[{ field: 'scheduled_at', sort: tab === 'upcoming' ? 'asc' : 'desc' }]}
        key={tab}
        emptyTitle={tab === 'upcoming' ? t('meetings.noneUpcoming') : t('meetings.none')}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 260 } }} />
            <OrgUnitSelect permission="meeting.view" allowAll value={unit} onChange={setUnit} sx={{ maxWidth: { md: 260 } }} />
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ maxWidth: { md: 180 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {['SCHEDULED', 'HELD', 'CANCELLED'].map((s) => <MenuItem key={s} value={s}>{t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
            </TextField>
          </Stack>
        }
      />
      <MeetingDialog open={scheduling} onClose={() => setScheduling(false)} />
    </>
  );
}
