import AddIcon from '@mui/icons-material/Add';
import ArrowDownIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import type { Meeting } from '@/api/types';
import { useFeedback } from '@/design-system';
import { actKeys, MEETING_TYPES, toLocalInput } from './api';
import { OrgUnitSelect, PARISH } from './shared';

interface Agenda { title: string; presenter: string }

/** Schedule a meeting (``meeting`` undefined) or change one. */
export function MeetingDialog({ open, onClose, meeting }: { open: boolean; onClose: () => void; meeting?: Meeting }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { toast, toastError } = useFeedback();
  const [unit, setUnit] = useState(PARISH);
  const [title, setTitle] = useState('');
  const [type, setType] = useState('REGULAR');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [location, setLocation] = useState('');
  const [description, setDescription] = useState('');
  const [agenda, setAgenda] = useState<Agenda[]>([]);
  const [notify, setNotify] = useState(true);
  useEffect(() => {
    if (!open) return;
    setUnit(meeting?.org_unit?.id ?? PARISH);
    setTitle(meeting?.title ?? '');
    setType(meeting?.meeting_type ?? 'REGULAR');
    setStart(toLocalInput(meeting?.scheduled_at));
    setEnd(toLocalInput(meeting?.ends_at));
    setLocation(meeting?.location ?? '');
    setDescription(meeting?.description ?? '');
    setAgenda(meeting?.agenda.map((a) => ({ title: a.title, presenter: a.presenter ?? '' })) ?? [{ title: t('meetings.openingPrayer'), presenter: '' }]);
    setNotify(true);
  }, [open, meeting, t]);
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        org_unit_id: unit || null, title: title.trim(), meeting_type: type, scheduled_at: start, ends_at: end || null,
        location: location.trim() || null, description: description.trim() || null, notify,
        agenda: agenda.filter((a) => a.title.trim()).map((a) => ({ title: a.title.trim(), presenter: a.presenter.trim() || null })),
      };
      return meeting ? (await api.put<Meeting>(`/meetings/${meeting.id}`, body)).data : (await api.post<Meeting>('/meetings', body)).data;
    },
    onSuccess: (m) => {
      qc.setQueryData([...actKeys.meetings, m.id], m);
      void qc.invalidateQueries({ queryKey: actKeys.meetings });
      void qc.invalidateQueries({ queryKey: actKeys.calendar });
      toast(meeting ? t('common.saved') : t('meetings.scheduled'));
      onClose();
      if (!meeting) navigate(`/meetings/${m.id}`);
    },
    onError: toastError,
  });
  const move = (i: number, d: -1 | 1) => {
    const next = [...agenda];
    [next[i], next[i + d]] = [next[i + d]!, next[i]!];
    setAgenda(next);
  };
  const valid = title.trim().length >= 2 && start && (!end || end > start);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{meeting ? t('meetings.edit') : t('meetings.schedule')}</DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ pt: 1 }}>
          <Grid size={{ xs: 12, md: 8 }}><TextField label={t('meetings.title')} value={title} onChange={(e) => setTitle(e.target.value)} required autoFocus /></Grid>
          <Grid size={{ xs: 12, md: 4 }}>
            <TextField select label={t('meetings.type')} value={type} onChange={(e) => setType(e.target.value)}>
              {MEETING_TYPES.map((m) => <MenuItem key={m} value={m}>{t(`meetings.types.${m}`)}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <OrgUnitSelect permission="meeting.create" autoSelect={!meeting} value={unit} onChange={setUnit}
              disabled={Boolean(meeting?.minutes)} current={meeting?.org_unit ?? null} />
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}><TextField label={t('activities.location')} value={location} onChange={(e) => setLocation(e.target.value)} /></Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField type="datetime-local" label={t('meetings.starts')} value={start} onChange={(e) => setStart(e.target.value)} required slotProps={{ inputLabel: { shrink: true } }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField type="datetime-local" label={t('meetings.ends')} value={end} onChange={(e) => setEnd(e.target.value)} slotProps={{ inputLabel: { shrink: true } }}
              error={Boolean(end && start && end <= start)} />
          </Grid>
          <Grid size={12}><TextField label={t('common.description')} value={description} onChange={(e) => setDescription(e.target.value)} multiline minRows={2} /></Grid>
          <Grid size={12}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('meetings.agenda')}</Typography>
            <Stack spacing={1} component="ol" sx={{ pl: 0, m: 0, listStyle: 'none' }} aria-label={t('meetings.agenda')}>
              {agenda.map((a, i) => (
                <Stack key={i} component="li" direction="row" spacing={1} alignItems="center">
                  <Typography variant="body2" color="text.secondary" sx={{ width: 20 }}>{i + 1}.</Typography>
                  <TextField size="small" label={t('meetings.item')} value={a.title} sx={{ flex: 3 }}
                    onChange={(e) => setAgenda(agenda.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                  <TextField size="small" label={t('meetings.presenter')} value={a.presenter} sx={{ flex: 2 }}
                    onChange={(e) => setAgenda(agenda.map((x, j) => (j === i ? { ...x, presenter: e.target.value } : x)))} />
                  <IconButton size="small" aria-label={t('workflow.moveUp')} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUpIcon fontSize="small" /></IconButton>
                  <IconButton size="small" aria-label={t('workflow.moveDown')} disabled={i === agenda.length - 1} onClick={() => move(i, 1)}><ArrowDownIcon fontSize="small" /></IconButton>
                  <IconButton size="small" aria-label={t('common.remove')} onClick={() => setAgenda(agenda.filter((_, j) => j !== i))}><DeleteIcon fontSize="small" /></IconButton>
                </Stack>
              ))}
            </Stack>
            <Button size="small" startIcon={<AddIcon />} sx={{ mt: 1 }} onClick={() => setAgenda([...agenda, { title: '', presenter: '' }])}>{t('meetings.addItem')}</Button>
          </Grid>
          <Grid size={12}>
            <FormControlLabel control={<Checkbox checked={notify} onChange={(e) => setNotify(e.target.checked)} />} label={t('meetings.notify')} />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate()}>{meeting ? t('common.save') : t('meetings.schedule')}</Button>
      </DialogActions>
    </Dialog>
  );
}
