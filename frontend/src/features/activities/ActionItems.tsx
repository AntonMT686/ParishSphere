import AddIcon from '@mui/icons-material/Add';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import LinearProgress from '@mui/material/LinearProgress';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Slider from '@mui/material/Slider';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/api/client';
import type { ActionItem, UserLookup } from '@/api/types';
import { StatusBadge, useFeedback } from '@/design-system';
import { UserPicker } from '@/features/org/pickers';
import { formatDate, formatDateTime } from '@/lib/format';
import { actKeys, useActionItem, useActionItems } from './api';
import { OrgUnitSelect, PARISH } from './shared';

export function ActionStatus({ item }: { item: Pick<ActionItem, 'status' | 'overdue'> }) {
  return <StatusBadge status={item.overdue ? 'OVERDUE' : item.status} />;
}

/** Create an action item from a meeting, an activity, or directly (organisation chosen in the dialog). */
export function NewActionDialog({ open, onClose, meetingId, activityId }: {
  open: boolean; onClose: () => void; meetingId?: string; activityId?: string;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const direct = !meetingId && !activityId;
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState<UserLookup | null>(null);
  const [ownerName, setOwnerName] = useState('');
  const [due, setDue] = useState('');
  const [unit, setUnit] = useState(PARISH);
  useEffect(() => { if (open) { setTitle(''); setDescription(''); setOwner(null); setOwnerName(''); setDue(''); } }, [open]);
  const create = useMutation({
    mutationFn: () => api.post('/action-items', {
      title: title.trim(), description: description.trim() || null, meeting_id: meetingId, activity_id: activityId,
      org_unit_id: direct ? unit || null : undefined, owner_user_id: owner?.id ?? null,
      owner_name: owner ? null : ownerName.trim() || null, due_date: due || null,
    }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: actKeys.actions }); void qc.invalidateQueries({ queryKey: actKeys.meetings }); toast(t('common.saved')); onClose(); },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('actions.new')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField label={t('actions.what')} value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus />
          <TextField label={t('common.description')} value={description} onChange={(e) => setDescription(e.target.value)} multiline minRows={2} />
          {direct && <OrgUnitSelect permission="action_item.create" autoSelect value={unit} onChange={setUnit} />}
          <UserPicker label={t('actions.responsibleUser')} value={owner} onChange={setOwner} />
          {!owner && <TextField label={t('actions.orName')} value={ownerName} onChange={(e) => setOwnerName(e.target.value)} helperText={t('actions.nameHint')} />}
          <TextField type="date" label={t('actions.due')} value={due} onChange={(e) => setDue(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={title.trim().length < 2 || (!owner && !ownerName.trim()) || create.isPending}
          onClick={() => create.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

/** Details, progress history and an update form for one action item. */
export function ActionItemDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const { data: item } = useActionItem(id);
  const [text, setText] = useState('');
  const [progress, setProgress] = useState(0);
  useEffect(() => { if (item) { setText(''); setProgress(item.progress_pct); } }, [item]);
  const update = useMutation({
    mutationFn: async (status?: string) =>
      (await api.post<ActionItem>(`/action-items/${id}/progress`, {
        text: text.trim() || null, progress_pct: progress !== item?.progress_pct ? progress : null, status: status ?? null,
      })).data,
    onSuccess: (a) => { qc.setQueryData([...actKeys.actions, id], a); void qc.invalidateQueries({ queryKey: actKeys.actions }); toast(t('common.saved')); },
    onError: toastError,
  });
  const source = item?.source;
  return (
    <Drawer anchor="right" open={Boolean(id)} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 460 } } }}>
      {item && (
        <Box sx={{ p: 3 }} role="region" aria-label={item.title}>
          <Typography variant="caption" color="text.secondary">{item.code}</Typography>
          <Typography variant="h3" sx={{ mb: 1 }}>{item.title}</Typography>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <ActionStatus item={item} />
            {item.due_date && <Typography variant="body2" color={item.overdue ? 'error' : 'text.secondary'}>{t('actions.dueOn', { date: formatDate(item.due_date) })}</Typography>}
          </Stack>
          {item.description && <Typography variant="body2" sx={{ mb: 2, whiteSpace: 'pre-line' }}>{item.description}</Typography>}
          <Stack spacing={0.5} sx={{ mb: 2 }}>
            <Typography variant="body2"><strong>{t('actions.responsible')}:</strong> {item.owner?.name ?? item.owner_name ?? '—'}</Typography>
            <Typography variant="body2"><strong>{t('activities.organisation')}:</strong> {item.org_unit?.name ?? t('activities.parishLevel')}</Typography>
            {source?.id && (
              <Typography variant="body2"><strong>{t('actions.from')}:</strong>{' '}
                <Link component={RouterLink} to={source.type === 'MEETING' ? `/meetings/${source.id}` : `/activities/${source.id}`} onClick={onClose}>{source.title}</Link>
              </Typography>
            )}
          </Stack>
          <Typography variant="body2" sx={{ mb: 0.5 }}>{t('actions.progress')}: {item.progress_pct}%</Typography>
          <LinearProgress variant="determinate" value={item.progress_pct} sx={{ mb: 3, height: 8, borderRadius: 4 }} />
          {item.can_update && (
            <Stack spacing={1.5} sx={{ mb: 3 }}>
              <Typography variant="subtitle2">{t('actions.update')}</Typography>
              <Slider value={progress} step={10} marks min={0} max={100} valueLabelDisplay="auto" aria-label={t('actions.progress')}
                onChange={(_e, v) => setProgress(v as number)} />
              <TextField label={t('actions.note')} value={text} onChange={(e) => setText(e.target.value)} multiline minRows={2} />
              <Stack direction="row" spacing={1}>
                <Button variant="contained" disabled={update.isPending || (!text.trim() && progress === item.progress_pct)} onClick={() => update.mutate(undefined)}>{t('actions.saveUpdate')}</Button>
                <Button color="success" disabled={update.isPending} onClick={() => update.mutate('DONE')}>{t('actions.markDone')}</Button>
                {item.can_edit && <Button color="inherit" disabled={update.isPending} onClick={() => update.mutate('CANCELLED')}>{t('actions.cancelItem')}</Button>}
              </Stack>
            </Stack>
          )}
          <Divider sx={{ mb: 2 }} />
          <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('actions.history')}</Typography>
          <Stack spacing={1.25} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('actions.history')}>
            {[...item.updates].reverse().map((u) => (
              <li key={u.id}>
                <Typography variant="body2">
                  {u.status && <Chip size="small" sx={{ mr: 1 }} label={t(`status.${u.status}`, { defaultValue: u.status })} />}
                  {u.progress_pct != null && `${u.progress_pct}% `}{u.text}
                </Typography>
                <Typography variant="caption" color="text.secondary">{u.by ?? '—'} · {formatDateTime(u.at)}</Typography>
              </li>
            ))}
            <li><Typography variant="caption" color="text.secondary">{t('actions.created', { date: formatDateTime(item.created_at) })}</Typography></li>
          </Stack>
        </Box>
      )}
    </Drawer>
  );
}

/** Action items of one meeting or activity. */
export function ActionItemsCard({ meetingId, activityId, canAdd }: { meetingId?: string; activityId?: string; canAdd: boolean }) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const { data } = useActionItems({ meeting: meetingId, activity: activityId });
  const items = data?.items ?? [];
  return (
    <Card>
      <CardHeader title={t('nav.actionItems')}
        action={canAdd && <Button size="small" startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('actions.new')}</Button>} />
      <CardContent sx={{ pt: 0 }}>
        {items.length === 0 && <Typography variant="body2" color="text.secondary">{t('actions.none')}</Typography>}
        <Stack spacing={1} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('nav.actionItems')}>
          {items.map((a) => (
            <Stack key={a.id} component="li" direction="row" spacing={1.5} alignItems="center"
              sx={{ cursor: 'pointer', p: 1, borderRadius: 1, '&:hover': { bgcolor: 'action.hover' } }} onClick={() => setOpen(a.id)}>
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap>{a.title}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {a.owner?.name ?? a.owner_name ?? '—'}{a.due_date ? ` · ${t('actions.dueOn', { date: formatDate(a.due_date) })}` : ''}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">{a.progress_pct}%</Typography>
              <ActionStatus item={a} />
            </Stack>
          ))}
        </Stack>
      </CardContent>
      <NewActionDialog open={adding} onClose={() => setAdding(false)} meetingId={meetingId} activityId={activityId} />
      <ActionItemDrawer id={open} onClose={() => setOpen(null)} />
    </Card>
  );
}

export const ACTION_STATUSES = ['ACTIVE', 'OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED'] as const;
export function ActionStatusSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { t } = useTranslation();
  return (
    <TextField select label={t('common.status')} value={value} onChange={(e) => onChange(e.target.value)} sx={{ maxWidth: { md: 200 } }}>
      <MenuItem value="">{t('common.all')}</MenuItem>
      {ACTION_STATUSES.map((s) => <MenuItem key={s} value={s}>{s === 'ACTIVE' ? t('actions.openItems') : t(`status.${s}`, { defaultValue: s })}</MenuItem>)}
    </TextField>
  );
}
