import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef, GridRowId } from '@mui/x-data-grid';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import type { WorkflowTaskItem } from '@/api/types';
import { DataTable, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { formatDateTime, formatMoney, timeAgo } from '@/lib/format';
import { ENTITY_TYPE_CODES, fetchTasks, useTaskSummary, wfKeys } from './api';
import { DelegationsDialog } from './DelegationsDialog';

export function MyApprovalsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [tab, setTab] = useState<'PENDING' | 'DONE'>('PENDING');
  const [entityType, setEntityType] = useState('');
  const [overdue, setOverdue] = useState(false);
  const [selected, setSelected] = useState<GridRowId[]>([]);
  const [delegations, setDelegations] = useState(false);
  const { data: summary } = useTaskSummary();
  const filters = { state: tab, entity_type: entityType || undefined, overdue: (tab === 'PENDING' && overdue) || undefined };
  const bulk = useMutation({
    mutationFn: async () =>
      (await api.post<{ approved: string[]; failed: { id: string; message: string }[] }>('/workflow/tasks/bulk-approve', { task_ids: selected })).data,
    onSuccess: (r) => {
      setSelected([]);
      void qc.invalidateQueries({ queryKey: wfKeys.all });
      toast(r.failed.length ? t('workflow.bulkPartial', { ok: r.approved.length, failed: r.failed.length }) : t('workflow.bulkDone', { count: r.approved.length }),
        r.failed.length ? 'warning' : 'success');
    },
    onError: toastError,
  });
  const columns: GridColDef<WorkflowTaskItem>[] = [
    {
      field: 'title', headerName: t('workflow.record'), flex: 1.6, minWidth: 240, sortable: false,
      renderCell: ({ row }) => (
        <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{row.instance.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap>
            {t(`workflow.entity.${row.instance.entity_type}`, { defaultValue: row.instance.entity_label })}
            {row.instance.org_unit ? ` · ${row.instance.org_unit.name}` : ''}
            {row.instance.amount != null ? ` · ${formatMoney(row.instance.amount)}` : ''}
          </Typography>
        </Stack>
      ),
    },
    { field: 'stage_name', headerName: t('workflow.stage'), flex: 1, minWidth: 170, sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: '100%' }}>
          <span>{row.stage_name}</span>
          {row.delegated_from && <Chip size="small" variant="outlined" label={t('workflow.forName', { name: row.delegated_from.name })} />}
          {row.is_escalation && <Chip size="small" color="warning" variant="outlined" label={t('workflow.escalation')} />}
        </Stack>
      ) },
    { field: 'submitted_by', headerName: t('workflow.submittedBy'), width: 170, sortable: false, valueGetter: (_v, r) => r.instance.submitted_by.name },
    tab === 'PENDING'
      ? { field: 'created_at', headerName: t('workflow.waiting'), width: 150,
          renderCell: ({ row }) => (
            <Stack justifyContent="center" sx={{ height: '100%', lineHeight: 1.3 }}>
              <span>{timeAgo(row.created_at)}</span>
              {row.overdue && <Typography variant="caption" color="error">{t('workflow.overdue')}</Typography>}
            </Stack>
          ) }
      : { field: 'acted_at', headerName: t('workflow.decidedOn'), width: 170, valueFormatter: (v: string) => formatDateTime(v) },
    tab === 'PENDING'
      ? { field: 'kind', headerName: '', width: 110, sortable: false, valueFormatter: (v: string) => t(`workflow.kind.${v}`) }
      : { field: 'status', headerName: t('workflow.yourDecisionShort'), width: 140, sortable: false, renderCell: ({ row }) => <StatusBadge status={row.status} /> },
  ];
  return (
    <>
      <PageHeader
        title={t('nav.myApprovals')}
        subtitle={summary ? t('workflow.inboxSubtitle', { pending: summary.pending, overdue: summary.overdue }) : undefined}
        breadcrumbs={[{ label: t('nav.approvals') }, { label: t('nav.myApprovals') }]}
        actions={<Button onClick={() => setDelegations(true)}>{t('workflow.delegations')}</Button>}
      />
      <Tabs value={tab} onChange={(_e, v: 'PENDING' | 'DONE') => { setTab(v); setSelected([]); }} sx={{ mb: 2 }}>
        <Tab value="PENDING" label={summary ? `${t('workflow.pendingTab')} (${summary.pending})` : t('workflow.pendingTab')} />
        <Tab value="DONE" label={t('workflow.doneTab')} />
      </Tabs>
      <DataTable<WorkflowTaskItem>
        queryKey={[...wfKeys.tasks, filters]}
        fetchPage={(req) => fetchTasks(req, filters)}
        columns={columns}
        onRowClick={(task) => navigate(`/approvals/${task.instance.id}`)}
        initialSort={tab === 'PENDING' ? [{ field: 'created_at', sort: 'asc' }] : [{ field: 'acted_at', sort: 'desc' }]}
        selection={tab === 'PENDING' ? { model: selected, onChange: setSelected } : undefined}
        emptyTitle={tab === 'PENDING' ? t('workflow.inboxEmpty') : undefined}
        toolbar={
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }}>
            <TextField select label={t('workflow.recordType')} value={entityType} onChange={(e) => setEntityType(e.target.value)} sx={{ maxWidth: { md: 240 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {ENTITY_TYPE_CODES.map((c) => <MenuItem key={c} value={c}>{t(`workflow.entity.${c}`)}</MenuItem>)}
            </TextField>
            {tab === 'PENDING' && (
              <FormControlLabel control={<Switch checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />} label={t('workflow.overdueOnly')} />
            )}
            {selected.length > 0 && (
              <Button variant="contained" color="success" sx={{ ml: { md: 'auto' } }} disabled={bulk.isPending} onClick={() => bulk.mutate()}>
                {t('workflow.approveSelected', { count: selected.length })}
              </Button>
            )}
          </Stack>
        }
      />
      <DelegationsDialog open={delegations} onClose={() => setDelegations(false)} />
    </>
  );
}
