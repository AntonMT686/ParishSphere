import AddIcon from '@mui/icons-material/Add';
import PrintIcon from '@mui/icons-material/PrintOutlined';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import type { NoticeListItem } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { DataTable, EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { downloadBlob } from '@/features/finance/api';
import { formatWallTime } from '@/lib/format';
import { CATEGORIES, fetchManaged, noticeKeys, STATES, useBoard } from './api';
import { NoticeCard } from './NoticeCard';

function Board() {
  const { t } = useTranslation();
  const { toastError } = useFeedback();
  const [category, setCategory] = useState('');
  const [q, setQ] = useState('');
  const { data, isLoading } = useBoard(category, useDeferredValue(q).trim());
  return (
    <>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap role="group" aria-label={t('notices.categoryLabel')}>
          <Chip label={t('common.all')} color={category === '' ? 'primary' : 'default'} onClick={() => setCategory('')} />
          {CATEGORIES.map((c) => <Chip key={c} label={t(`notices.category.${c}`)} color={category === c ? 'primary' : 'default'} onClick={() => setCategory(c)} />)}
        </Stack>
        <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 260 }, ml: { md: 'auto' } }} />
        <Button startIcon={<PrintIcon />} onClick={() => downloadBlob(`/notices/bulletin.pdf${category ? `?category=${category}` : ''}`, 'parish-notices.pdf').catch(toastError)}>
          {t('notices.print')}
        </Button>
      </Stack>
      {isLoading ? <Skeleton variant="rounded" height={240} /> : data?.items.length === 0 ? (
        <EmptyState title={t('notices.nothing')} description={t('notices.nothingHint')} />
      ) : (
        <Grid container spacing={2}>
          {data?.items.map((n) => <Grid key={n.id} size={{ xs: 12, md: 6, xl: 4 }}><NoticeCard n={n} /></Grid>)}
        </Grid>
      )}
    </>
  );
}

function Manage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [state, setState] = useState('');
  const [q, setQ] = useState('');
  const filters = { state, q: useDeferredValue(q).trim() };
  const columns: GridColDef<NoticeListItem>[] = [
    {
      field: 'title', headerName: t('notices.title'), flex: 1.6, minWidth: 240,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>{row.code} · {t(`notices.category.${row.category}`)}{row.is_important ? ` · ${t('notices.important')}` : ''}</Typography>
        </Stack>
      ),
    },
    { field: 'audience', headerName: t('notices.audience'), flex: 1, minWidth: 160, sortable: false, valueGetter: (_v, r) => (r.audience_all ? t('notices.everyone') : r.audience.map((a) => a.name).join(', ')) },
    { field: 'publish_at', headerName: t('notices.publishAt'), width: 180, valueFormatter: (v: string) => formatWallTime(v) },
    { field: 'state', headerName: t('common.status'), width: 140, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.state} /> },
  ];
  return (
    <DataTable<NoticeListItem>
      queryKey={[...noticeKeys.all, 'manage', filters]}
      fetchPage={(req) => fetchManaged(req, filters)}
      columns={columns}
      onRowClick={(n) => navigate(`/notices/${n.id}`)}
      emptyTitle={t('notices.noneManaged')}
      toolbar={
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
          <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 260 } }} />
          <TextField select label={t('common.status')} value={state} onChange={(e) => setState(e.target.value)} sx={{ maxWidth: { md: 200 } }}>
            <MenuItem value="">{t('common.all')}</MenuItem>
            {STATES.map((s) => <MenuItem key={s} value={s}>{t(`notices.state.${s}`)}</MenuItem>)}
          </TextField>
        </Stack>
      }
    />
  );
}

export function NoticesPage() {
  const { t } = useTranslation();
  const can = useCan();
  const manager = can(['notice.create', 'notice.update', 'notice.publish']);
  const [tab, setTab] = useState<'board' | 'manage'>('board');
  return (
    <>
      <PageHeader title={t('nav.notices')} subtitle={t('notices.subtitle')} breadcrumbs={[{ label: t('nav.content') }, { label: t('nav.notices') }]}
        actions={can('notice.create') && <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/notices/new">{t('notices.new')}</Button>} />
      {manager && (
        <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab value="board" label={t('notices.board')} />
          <Tab value="manage" label={t('notices.manage')} />
        </Tabs>
      )}
      {tab === 'board' ? <Board /> : <Manage />}
    </>
  );
}
