import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutline';
import CancelIcon from '@mui/icons-material/Cancel';
import ScheduleIcon from '@mui/icons-material/Schedule';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import type { WorkflowInstance, WorkflowStageState } from '@/api/types';
import { formatDateTime, parseApiDate } from '@/lib/format';

const TASK_COLOR: Record<string, 'success' | 'error' | 'warning' | 'default' | 'info'> = {
  APPROVED: 'success', REJECTED: 'error', RETURNED: 'warning', PENDING: 'info', DELEGATED: 'default', CANCELLED: 'default',
};

function StageIcon({ stage, failed }: { stage: WorkflowStageState; failed: boolean }) {
  if (stage.state === 'DONE') return <CheckCircleIcon color="success" />;
  if (stage.state === 'SKIPPED') return <RemoveCircleOutlineIcon color="disabled" />;
  if (stage.state === 'CURRENT') return failed ? <CancelIcon color="error" /> : <ScheduleIcon color="primary" />;
  return <RadioButtonUncheckedIcon color="disabled" />;
}

/** Stages of the current cycle with each reviewer's decision, then the full history of actions. */
export function ApprovalTimeline({ instance, showHistory = true }: { instance: WorkflowInstance; showHistory?: boolean }) {
  const { t } = useTranslation();
  const failed = instance.status === 'REJECTED' || instance.status === 'REWORK';
  const quorum = (q: string) => (q === 'ANY' ? t('workflow.quorumAny') : q === 'ALL' ? t('workflow.quorumAll') : t('workflow.quorumN', { n: q }));
  return (
    <Box>
      <Stack component="ol" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('workflow.stages')}>
        {instance.stages.map((s, i) => (
          <Box component="li" key={s.index} sx={{ display: 'flex', gap: 1.5 }}>
            <Stack alignItems="center">
              <StageIcon stage={s} failed={failed} />
              {i < instance.stages.length - 1 && <Box sx={{ width: 2, flexGrow: 1, bgcolor: 'divider', my: 0.5, minHeight: 16 }} />}
            </Stack>
            <Box sx={{ pb: 2, flexGrow: 1, minWidth: 0 }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography variant="subtitle2">{s.name}</Typography>
                {s.state === 'SKIPPED' && <Chip size="small" label={t('workflow.skipped')} />}
                {s.tasks.length > 1 && <Typography variant="caption" color="text.secondary">{quorum(s.quorum)}</Typography>}
              </Stack>
              <Stack spacing={0.75} sx={{ mt: 0.75 }}>
                {s.tasks.map((task) => (
                  <Box key={task.id}>
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                      <Typography variant="body2">{task.assignee.name}</Typography>
                      <Chip size="small" variant={task.status === 'PENDING' ? 'outlined' : 'filled'}
                        color={TASK_COLOR[task.status] ?? 'default'} label={t(`workflow.taskStatus.${task.status}`)} />
                      {task.delegated_from && (
                        <Typography variant="caption" color="text.secondary">{t('workflow.onBehalfOf', { name: task.delegated_from.name })}</Typography>
                      )}
                      {task.is_escalation && <Chip size="small" color="warning" variant="outlined" label={t('workflow.escalation')} />}
                      {task.acted_at && <Typography variant="caption" color="text.secondary">{formatDateTime(task.acted_at)}</Typography>}
                      {task.status === 'PENDING' && task.due_at && (
                        <Tooltip title={formatDateTime(task.due_at)}>
                          <Typography variant="caption" color={parseApiDate(task.due_at) < new Date() ? 'error' : 'text.secondary'}>
                            {t('workflow.due', { when: formatDateTime(task.due_at) })}
                          </Typography>
                        </Tooltip>
                      )}
                    </Stack>
                    {task.acted_by && (
                      <Typography variant="caption" color="text.secondary" component="div">{t('workflow.decidedBy', { name: task.acted_by.name })}</Typography>
                    )}
                    {task.comment && (
                      <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic', mt: 0.25 }}>“{task.comment}”</Typography>
                    )}
                  </Box>
                ))}
              </Stack>
            </Box>
          </Box>
        ))}
      </Stack>
      {showHistory && (
        <>
          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('workflow.history')}</Typography>
          <Stack component="ul" spacing={1.25} sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('workflow.history')}>
            {instance.actions.map((a, i) => {
              const newCycle = i > 0 && a.cycle !== instance.actions[i - 1]!.cycle;
              return (
                <Box component="li" key={a.id}>
                  {newCycle && <Divider textAlign="left" sx={{ mb: 1, typography: 'caption', color: 'text.secondary' }}>{t('workflow.cycle', { n: a.cycle })}</Divider>}
                  <Typography variant="body2">
                    <strong>{t(`workflow.action.${a.action}`, { defaultValue: a.action })}</strong>
                    {a.stage_name && a.action !== 'SUBMIT' && a.action !== 'RESUBMIT' && <> · {a.stage_name}</>}
                    {' — '}
                    {a.actor ? a.actor.name : t('workflow.system')}
                    {a.on_behalf_of && <> ({t('workflow.onBehalfOf', { name: a.on_behalf_of.name })})</>}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">{formatDateTime(a.created_at)}</Typography>
                  {a.comment && <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>“{a.comment}”</Typography>}
                </Box>
              );
            })}
          </Stack>
        </>
      )}
    </Box>
  );
}
