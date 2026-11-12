import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { WorkflowInstanceSummary } from '@/api/types';
import { DataTable, PageHeader, StatusBadge } from '@/design-system';
import { formatDateTime } from '@/lib/format';
import { ENTITY_TYPE_CODES, fetchInstances, wfKeys } from './api';

const STATUSES = ['ACTIVE', 'IN_PROGRESS', 'REWORK', 'APPROVED', 'REJECTED', 'CANCELLED'];

export function SubmittedPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('');
  const [entityType, setEntityType] = useState('');
  const filters = { q: useDeferredValue(q).trim(), status, entity_type: entityType };
  const columns: GridColDef<WorkflowInstanceSummary>[] = [
    {
      field: 'title', headerName: t('workflow.record'), flex: 1.5, minWidth: 240,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {t(`workflow.entity.${row.entity_type}`, { defaultValue: row.entity_label })}{row.org_unit ? ` · ${row.org_unit.name}` : ''}
          </Typography>
        </Stack>
      ),
    },
    { field: 'status', headerName: t('common.status'), width: 140, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
    {
      field: 'stage_name', headerName: t('workflow.progress'), flex: 1.2, minWidth: 220, sortable: false,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" noWrap>
            {row.status === 'IN_PROGRESS' ? t('workflow.stageOf', { n: row.stage_index + 1, total: row.stage_count, name: row.stage_name }) : '—'}
          </Typography>
          {row.status === 'IN_PROGRESS' && row.pending_with.length > 0 && (
            <Typography variant="caption" color="text.secondary" noWrap>{t('workflow.withNames', { names: row.pending_with.join(', ') })}</Typography>
          )}
        </Stack>
      ),
    },
    { field: 'submitted_at', headerName: t('workflow.submittedAt'), width: 180, valueFormatter: (v: string) => formatDateTime(v) },
  ];
  return (
    <>
      <PageHeader title={t('nav.submitted')} subtitle={t('workflow.submittedSubtitle')}
        breadcrumbs={[{ label: t('nav.approvals') }, { label: t('nav.submitted') }]} />
      <DataTable<WorkflowInstanceSummary>
        queryKey={[...wfKeys.instances, 'mine', filters]}
        fetchPage={(req) => fetchInstances(req, filters)}
        columns={columns}
        onRowClick={(i) => navigate(`/approvals/${i.id}`)}
        initialSort={[{ field: 'submitted_at', sort: 'desc' }]}
        emptyTitle={t('workflow.nothingSubmitted')}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
            <TextField label={t('common.search')} value={q} onChange={(e) => setQ(e.target.value)} sx={{ maxWidth: { md: 300 } }} />
            <TextField select label={t('common.status')} value={status} onChange={(e) => setStatus(e.target.value)} sx={{ maxWidth: { md: 200 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {STATUSES.map((s) => <MenuItem key={s} value={s}>{s === 'ACTIVE' ? t('workflow.openOnly') : t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
            </TextField>
            <TextField select label={t('workflow.recordType')} value={entityType} onChange={(e) => setEntityType(e.target.value)} sx={{ maxWidth: { md: 240 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {ENTITY_TYPE_CODES.map((c) => <MenuItem key={c} value={c}>{t(`workflow.entity.${c}`)}</MenuItem>)}
            </TextField>
          </Stack>
        }
      />
    </>
  );
}
