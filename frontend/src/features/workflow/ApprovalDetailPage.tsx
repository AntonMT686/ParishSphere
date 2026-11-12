import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { UserLookup, WorkflowInstance } from '@/api/types';
import { useAuthStore } from '@/auth/authStore';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { UserPicker } from '@/features/org/pickers';
import { formatDateTime, formatMoney } from '@/lib/format';
import { ApprovalTimeline } from './ApprovalTimeline';
import { useInstance, wfKeys } from './api';

function useInvalidate() {
  const qc = useQueryClient();
  return (inst?: WorkflowInstance) => {
    if (inst) qc.setQueryData([...wfKeys.instances, inst.id], inst);
    void qc.invalidateQueries({ queryKey: wfKeys.all });
  };
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div">{children}</Typography>
    </div>
  );
}

/** Approve / return / reject / delegate a pending task (own, or on someone's behalf for administrators). */
export function DecisionPanel({ instance }: { instance: WorkflowInstance }) {
  const { t } = useTranslation();
  const { toast, toastError, confirm } = useFeedback();
  const invalidate = useInvalidate();
  const pendingTasks = instance.stages.flatMap((s) => s.tasks.filter((x) => x.status === 'PENDING'));
  const [taskId, setTaskId] = useState(instance.my_task ?? pendingTasks[0]?.id ?? '');
  const [comment, setComment] = useState('');
  const [delegating, setDelegating] = useState(false);
  const [delegate, setDelegate] = useState<UserLookup | null>(null);
  const onBehalf = !instance.my_task;
  const decide = useMutation({
    mutationFn: async (action: string) =>
      (await api.post<WorkflowInstance>(`/workflow/tasks/${taskId}/act`, {
        action, comment: comment.trim() || null, delegate_user_id: action === 'DELEGATE' ? delegate?.id : undefined,
      })).data,
    onSuccess: (inst, action) => {
      invalidate(inst);
      toast(t(`workflow.done.${action}`));
      setComment('');
      setDelegating(false);
      setDelegate(null);
    },
    onError: toastError,
  });
  const needComment = (action: string) => (action === 'REJECT' || action === 'RETURN') && !comment.trim();
  const run = async (action: string) => {
    if (action === 'REJECT' && !(await confirm({ title: t('workflow.rejectConfirm'), message: t('workflow.rejectHint'), destructive: true }))) return;
    decide.mutate(action);
  };
  if (!taskId) return null;
  return (
    <Card sx={{ mb: 2, borderColor: 'primary.main', borderWidth: 2 }}>
      <CardHeader title={onBehalf ? t('workflow.decideOnBehalf') : t('workflow.yourDecision')}
        subheader={instance.stage_name ?? undefined} />
      <CardContent sx={{ pt: 0 }}>
        <Stack spacing={2}>
          {onBehalf && (
            <>
              <Alert severity="warning">{t('workflow.overrideHint')}</Alert>
              <TextField select label={t('workflow.taskOf')} value={taskId} onChange={(e) => setTaskId(e.target.value)}>
                {pendingTasks.map((x) => <MenuItem key={x.id} value={x.id}>{x.assignee.name}</MenuItem>)}
              </TextField>
            </>
          )}
          <TextField label={t('workflow.comment')} value={comment} onChange={(e) => setComment(e.target.value)} multiline minRows={2}
            helperText={t('workflow.commentHint')} />
          {delegating ? (
            <Stack spacing={1.5}>
              <UserPicker label={t('workflow.delegateTo')} value={delegate} onChange={setDelegate} />
              <Stack direction="row" spacing={1}>
                <Button variant="contained" disabled={!delegate || decide.isPending} onClick={() => void run('DELEGATE')}>{t('workflow.delegate')}</Button>
                <Button onClick={() => setDelegating(false)}>{t('common.cancel')}</Button>
              </Stack>
            </Stack>
          ) : (
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <Button variant="contained" color="success" disabled={decide.isPending} onClick={() => void run('APPROVE')}>{t('workflow.approve')}</Button>
              <Button variant="outlined" color="warning" disabled={decide.isPending || needComment('RETURN')} onClick={() => void run('RETURN')}>{t('workflow.return')}</Button>
              <Button variant="outlined" color="error" disabled={decide.isPending || needComment('REJECT')} onClick={() => void run('REJECT')}>{t('workflow.reject')}</Button>
              <Button disabled={decide.isPending} onClick={() => setDelegating(true)}>{t('workflow.delegate')}</Button>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

function SubmitterActions({ instance }: { instance: WorkflowInstance }) {
  const { t } = useTranslation();
  const { toast, toastError, confirm } = useFeedback();
  const invalidate = useInvalidate();
  const [comment, setComment] = useState('');
  const call = useMutation({
    mutationFn: async (what: 'withdraw' | 'resubmit') =>
      (await api.post<WorkflowInstance>(`/workflow/instances/${instance.id}/${what}`, { comment: comment.trim() || null })).data,
    onSuccess: (inst, what) => { invalidate(inst); setComment(''); toast(t(`workflow.done.${what}`)); },
    onError: toastError,
  });
  if (!instance.can_withdraw && !instance.can_resubmit) return null;
  return (
    <Card sx={{ mb: 2 }}>
      <CardHeader title={t('workflow.yourSubmission')} />
      <CardContent sx={{ pt: 0 }}>
        <Stack spacing={1.5}>
          {instance.status === 'REWORK' && <Alert severity="warning">{t('workflow.reworkHint')}</Alert>}
          <TextField label={t('workflow.comment')} value={comment} onChange={(e) => setComment(e.target.value)} />
          <Stack direction="row" spacing={1}>
            {instance.can_resubmit && (
              <Button variant="contained" disabled={call.isPending} onClick={() => call.mutate('resubmit')}>{t('workflow.resubmit')}</Button>
            )}
            {instance.can_withdraw && (
              <Button color="error" disabled={call.isPending} onClick={async () => {
                if (await confirm({ title: t('workflow.withdrawConfirm'), destructive: true })) call.mutate('withdraw');
              }}>{t('workflow.withdraw')}</Button>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

export function ApprovalDetailPage() {
  const { instanceId = '' } = useParams();
  const { t } = useTranslation();
  const { data: inst, isError } = useInstance(instanceId);
  const meId = useAuthStore((s) => s.user?.id);
  if (isError) return <EmptyState title={t('workflow.notFound')} />;
  if (!inst) return <Skeleton variant="rounded" height={420} />;
  const canDecide = inst.status === 'IN_PROGRESS' && (Boolean(inst.my_task) || inst.can_override);
  return (
    <>
      <PageHeader
        title={inst.title}
        subtitle={`${t(`workflow.entity.${inst.entity_type}`, { defaultValue: inst.entity_label })}${inst.org_unit ? ` · ${inst.org_unit.name}` : ''}`}
        breadcrumbs={[
          { label: t('nav.approvals') },
          inst.submitted_by.id === meId && !inst.my_task
            ? { label: t('nav.submitted'), to: '/approvals/submitted' }
            : { label: t('nav.myApprovals'), to: '/approvals' },
          { label: inst.title },
        ]}
        actions={inst.link && <Button component={RouterLink} to={inst.link}>{t('workflow.openRecord')}</Button>}
      />
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          {canDecide && <DecisionPanel key={inst.my_task ?? 'override'} instance={inst} />}
          <SubmitterActions instance={inst} />
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                <StatusBadge status={inst.status} />
                {inst.cycle > 1 && <Typography variant="caption" color="text.secondary">{t('workflow.cycle', { n: inst.cycle })}</Typography>}
              </Stack>
              <Grid container spacing={2}>
                <Grid size={6}><Fact label={t('workflow.submittedBy')}>{inst.submitted_by.name}</Fact></Grid>
                <Grid size={6}><Fact label={t('workflow.submittedAt')}>{formatDateTime(inst.submitted_at)}</Fact></Grid>
                {inst.amount != null && <Grid size={6}><Fact label={t('workflow.amount')}>{formatMoney(inst.amount)}</Fact></Grid>}
                {inst.category && <Grid size={6}><Fact label={t('workflow.category')}>{inst.category}</Fact></Grid>}
                <Grid size={6}><Fact label={t('workflow.workflow')}>{`${inst.definition.name} (v${inst.definition.version})`}</Fact></Grid>
                {inst.completed_at && <Grid size={6}><Fact label={t('workflow.completedAt')}>{formatDateTime(inst.completed_at)}</Fact></Grid>}
                {inst.status === 'IN_PROGRESS' && (
                  <Grid size={12}><Fact label={t('workflow.waitingFor')}>{inst.pending_with.join(', ') || '—'}</Fact></Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card>
            <CardHeader title={t('workflow.timeline')} />
            <CardContent sx={{ pt: 0 }}><ApprovalTimeline instance={inst} /></CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
