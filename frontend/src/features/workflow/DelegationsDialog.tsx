import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { UserLookup } from '@/api/types';
import { useAuthStore } from '@/auth/authStore';
import { useFeedback } from '@/design-system';
import { UserPicker } from '@/features/org/pickers';
import { formatDate } from '@/lib/format';
import { useDelegations, wfKeys } from './api';

const today = () => new Date().toISOString().slice(0, 10);

/** "While I am away, send my approvals to …" */
export function DelegationsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const { toast, toastError } = useFeedback();
  const { data = [] } = useDelegations(false, open);
  const [delegate, setDelegate] = useState<UserLookup | null>(null);
  const [from, setFrom] = useState(today());
  const [to, setTo] = useState('');
  const [reason, setReason] = useState('');
  useEffect(() => { if (open) { setDelegate(null); setFrom(today()); setTo(''); setReason(''); } }, [open]);
  const refresh = () => void qc.invalidateQueries({ queryKey: wfKeys.delegations });
  const create = useMutation({
    mutationFn: () => api.post('/workflow/delegations', {
      delegate_user_id: delegate?.id, valid_from: from || null, valid_to: to || null, reason: reason || null,
    }),
    onSuccess: () => { refresh(); toast(t('common.saved')); setDelegate(null); setReason(''); setTo(''); },
    onError: toastError,
  });
  const end = useMutation({
    mutationFn: (id: string) => api.post(`/workflow/delegations/${id}/end`),
    onSuccess: () => { refresh(); toast(t('common.saved')); },
    onError: toastError,
  });
  const rows = data.filter((d) => !d.ended_at);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('workflow.delegations')}</DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 2 }}>{t('workflow.delegationHint')}</Alert>
        <Stack spacing={1.5}>
          <UserPicker label={t('workflow.delegateTo')} value={delegate} onChange={setDelegate} />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField type="date" label={t('workflow.from')} value={from} onChange={(e) => setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
            <TextField type="date" label={t('workflow.until')} value={to} onChange={(e) => setTo(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          </Stack>
          <TextField label={t('workflow.reason')} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t('workflow.reasonPlaceholder')} />
          <div>
            <Button variant="contained" disabled={!delegate || create.isPending} onClick={() => create.mutate()}>{t('workflow.addDelegation')}</Button>
          </div>
        </Stack>
        <Divider sx={{ my: 2 }} />
        {rows.length === 0 && <Typography variant="body2" color="text.secondary">{t('workflow.noDelegations')}</Typography>}
        <Stack spacing={1.5}>
          {rows.map((d) => {
            const outgoing = d.delegator.id === me?.id;
            return (
              <Stack key={d.id} direction="row" spacing={1} alignItems="center" justifyContent="space-between">
                <div>
                  <Typography variant="body2">
                    {outgoing ? t('workflow.myTasksGoTo', { name: d.delegate.name }) : t('workflow.youActFor', { name: d.delegator.name })}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatDate(d.valid_from)} – {d.valid_to ? formatDate(d.valid_to) : t('workflow.untilEnded')}{d.reason ? ` · ${d.reason}` : ''}
                  </Typography>
                </div>
                <Stack direction="row" spacing={1} alignItems="center">
                  {d.active ? <Chip size="small" color="success" label={t('workflow.activeNow')} /> : <Chip size="small" label={t('workflow.scheduled')} />}
                  {outgoing && <Button size="small" color="error" onClick={() => end.mutate(d.id)}>{t('workflow.endDelegation')}</Button>}
                </Stack>
              </Stack>
            );
          })}
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>{t('common.close')}</Button></DialogActions>
    </Dialog>
  );
}
