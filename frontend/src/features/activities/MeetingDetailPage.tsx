import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import EditIcon from '@mui/icons-material/EditOutlined';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdfOutlined';
import SendIcon from '@mui/icons-material/SendOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { AttendanceRow, Meeting, MinutesInput } from '@/api/types';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { wfKeys } from '@/features/workflow/api';
import { formatDateTime, formatWallTime } from '@/lib/format';
import { ActionItemsCard } from './ActionItems';
import { actKeys, useAttendance, useMeeting } from './api';
import { MeetingDialog } from './MeetingDialog';
import { ApprovalSection, AttachmentsCard, Fact } from './shared';

function useSetMeeting() {
  const qc = useQueryClient();
  return (m: Meeting) => {
    qc.setQueryData([...actKeys.meetings, m.id], m);
    void qc.invalidateQueries({ queryKey: actKeys.meetings });
    void qc.invalidateQueries({ queryKey: wfKeys.all });
  };
}

// ----------------------------------------------------------------------------- attendance
function AttendanceTab({ meeting }: { meeting: Meeting }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const { data } = useAttendance(meeting.id);
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [guest, setGuest] = useState('');
  useEffect(() => { if (data) setRows(data.rows); }, [data]);
  const editable = meeting.can.edit && meeting.status !== 'CANCELLED';
  const save = useMutation({
    mutationFn: async () => (await api.put(`/meetings/${meeting.id}/attendance`, { rows })).data,
    onSuccess: (d) => {
      qc.setQueryData([...actKeys.meetings, meeting.id, 'attendance'], d);
      void qc.invalidateQueries({ queryKey: actKeys.meetings });
      toast(t('meetings.attendanceSaved'));
    },
    onError: toastError,
  });
  if (!data) return <Skeleton variant="rounded" height={240} />;
  const present = rows.filter((r) => r.status === 'PRESENT').length;
  const setAll = (status: AttendanceRow['status']) => setRows(rows.map((r) => ({ ...r, status })));
  return (
    <Card>
      <CardHeader title={t('meetings.attendance')} subheader={t('meetings.presentOf', { present, total: rows.length })}
        action={editable && rows.length > 0 && <Button size="small" onClick={() => setAll('PRESENT')}>{t('meetings.allPresent')}</Button>} />
      <CardContent sx={{ pt: 0 }}>
        {!data.recorded && rows.length > 0 && <Alert severity="info" sx={{ mb: 2 }}>{t('meetings.attendancePrefill')}</Alert>}
        {rows.length === 0 && <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{t('meetings.noInvitees')}</Typography>}
        {rows.length > 0 && (
          <Table size="small" aria-label={t('meetings.attendance')}>
            <TableHead><TableRow><TableCell>{t('common.name')}</TableCell><TableCell align="right">{t('common.status')}</TableCell></TableRow></TableHead>
            <TableBody>
              {rows.map((r, i) => (
                <TableRow key={`${r.member_id ?? r.family_id ?? 'g'}-${i}`}>
                  <TableCell>
                    {r.name}
                    {!r.member_id && !r.family_id && <Chip size="small" variant="outlined" label={t('meetings.guest')} sx={{ ml: 1 }} />}
                  </TableCell>
                  <TableCell align="right">
                    <ToggleButtonGroup size="small" exclusive value={r.status} disabled={!editable} aria-label={r.name}
                      onChange={(_e, v) => v && setRows(rows.map((x, j) => (j === i ? { ...x, status: v } : x)))}>
                      <ToggleButton value="PRESENT" color="success">{t('meetings.present')}</ToggleButton>
                      <ToggleButton value="EXCUSED" color="warning">{t('meetings.excused')}</ToggleButton>
                      <ToggleButton value="ABSENT">{t('meetings.absent')}</ToggleButton>
                    </ToggleButtonGroup>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {editable && (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 2 }}>
            <TextField size="small" label={t('meetings.addGuest')} value={guest} onChange={(e) => setGuest(e.target.value)} />
            <Button size="small" startIcon={<AddIcon />} disabled={!guest.trim()} onClick={() => {
              setRows([...rows, { name: guest.trim(), status: 'PRESENT', member_id: null, family_id: null, remarks: null }]);
              setGuest('');
            }}>{t('common.add')}</Button>
            <Box sx={{ flexGrow: 1 }} />
            <Button variant="contained" disabled={save.isPending || rows.length === 0} onClick={() => save.mutate()}>{t('meetings.saveAttendance')}</Button>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------------- minutes
const emptyMinutes = (): MinutesInput => ({ summary: '', points: [{ topic: '', discussion: '' }], resolutions: [] });

function MinutesTab({ meeting }: { meeting: Meeting }) {
  const { t } = useTranslation();
  const { toast, toastError } = useFeedback();
  const setMeeting = useSetMeeting();
  const mm = meeting.minutes;
  const [form, setForm] = useState<MinutesInput>(emptyMinutes());
  const [editing, setEditing] = useState(false);
  useEffect(() => {
    setForm(mm ? { summary: mm.summary ?? '', points: mm.points.length ? mm.points : [{ topic: '', discussion: '' }], resolutions: mm.resolutions } : emptyMinutes());
  }, [mm]);
  const canWrite = mm ? mm.can_edit : meeting.can.edit;
  const save = useMutation({
    mutationFn: async () => (await api.put<Meeting>(`/meetings/${meeting.id}/minutes`, {
      summary: form.summary?.trim() || null,
      points: (form.points ?? []).filter((p) => p.topic.trim()),
      resolutions: (form.resolutions ?? []).filter((r) => r.text.trim()),
    })).data,
    onSuccess: (m) => { setMeeting(m); setEditing(false); toast(t('meetings.minutesSaved')); },
    onError: toastError,
  });
  const submit = useMutation({
    mutationFn: async () => (await api.post<Meeting>(`/meetings/${meeting.id}/minutes/submit`, {})).data,
    onSuccess: (m) => { setMeeting(m); toast(t('activities.submitted')); },
    onError: toastError,
  });
  const points = form.points ?? [];
  const resolutions = form.resolutions ?? [];
  if (!mm && !editing) {
    return (
      <Card><CardContent>
        <EmptyState title={t('meetings.noMinutes')} description={canWrite ? t('meetings.noMinutesHint') : undefined}
          action={canWrite && <Button variant="contained" onClick={() => setEditing(true)}>{t('meetings.writeMinutes')}</Button>} />
      </CardContent></Card>
    );
  }
  if (mm && !editing) {
    return (
      <Card>
        <CardHeader title={t('meetings.minutes')} subheader={mm.recorded_by ? t('meetings.recordedBy', { name: mm.recorded_by }) : undefined}
          action={
            <Stack direction="row" spacing={1} alignItems="center">
              <StatusBadge status={mm.status} />
              <Button size="small" startIcon={<PictureAsPdfIcon />} onClick={() => void downloadPdf(meeting)}>{t('meetings.pdf')}</Button>
              {mm.can_edit && <Button size="small" startIcon={<EditIcon />} onClick={() => setEditing(true)}>{t('common.edit')}</Button>}
              {mm.can_submit && <Button size="small" variant="contained" startIcon={<SendIcon />} disabled={submit.isPending} onClick={() => submit.mutate()}>
                {mm.status === 'REWORK' ? t('activities.resubmit') : t('meetings.submitMinutes')}</Button>}
            </Stack>
          } />
        <CardContent sx={{ pt: 0 }}>
          {mm.status === 'REWORK' && <Alert severity="warning" sx={{ mb: 2 }}>{t('activities.reworkBanner')}</Alert>}
          {mm.summary && <Box sx={{ mb: 2 }}><Fact label={t('meetings.summary')}>{mm.summary}</Fact></Box>}
          {mm.points.length > 0 && (
            <>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('meetings.discussion')}</Typography>
              <Stack component="ol" spacing={1} sx={{ pl: 2.5, mt: 0, mb: 2 }}>
                {mm.points.map((p, i) => (
                  <li key={i}><Typography variant="body2" fontWeight={600}>{p.topic}</Typography>
                    {p.discussion && <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>{p.discussion}</Typography>}</li>
                ))}
              </Stack>
            </>
          )}
          {mm.resolutions.length > 0 && (
            <>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('meetings.resolutions')}</Typography>
              <Stack component="ol" spacing={1} sx={{ pl: 2.5, m: 0 }}>
                {mm.resolutions.map((r, i) => (
                  <li key={i}><Typography variant="body2">{r.text} <Chip size="small" sx={{ ml: 0.5 }}
                    color={r.decision === 'PASSED' ? 'success' : r.decision === 'REJECTED' ? 'error' : 'default'} label={t(`meetings.decision.${r.decision}`)} /></Typography></li>
                ))}
              </Stack>
            </>
          )}
          {mm.approved_at && <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 2 }}>{t('meetings.approvedOn', { date: formatDateTime(mm.approved_at) })}</Typography>}
        </CardContent>
      </Card>
    );
  }
  return (
    <Card component="section" aria-label={t('meetings.minutesEditor')}>
      <CardHeader title={t('meetings.minutesEditor')} />
      <CardContent sx={{ pt: 0 }}>
        <Stack spacing={2}>
          <TextField label={t('meetings.summary')} value={form.summary ?? ''} onChange={(e) => setForm({ ...form, summary: e.target.value })} multiline minRows={3} />
          <Typography variant="subtitle2">{t('meetings.discussion')}</Typography>
          {points.map((p, i) => (
            <Stack key={i} direction="row" spacing={1} alignItems="flex-start">
              <Typography variant="body2" sx={{ pt: 1, width: 20 }}>{i + 1}.</Typography>
              <Stack spacing={1} sx={{ flexGrow: 1 }}>
                <TextField size="small" label={t('meetings.topic')} value={p.topic}
                  onChange={(e) => setForm({ ...form, points: points.map((x, j) => (j === i ? { ...x, topic: e.target.value } : x)) })} />
                <TextField size="small" label={t('meetings.discussed')} value={p.discussion ?? ''} multiline minRows={2}
                  onChange={(e) => setForm({ ...form, points: points.map((x, j) => (j === i ? { ...x, discussion: e.target.value } : x)) })} />
              </Stack>
              <IconButton aria-label={t('common.remove')} onClick={() => setForm({ ...form, points: points.filter((_, j) => j !== i) })}><DeleteIcon /></IconButton>
            </Stack>
          ))}
          <div><Button size="small" startIcon={<AddIcon />} onClick={() => setForm({ ...form, points: [...points, { topic: '', discussion: '' }] })}>{t('meetings.addPoint')}</Button></div>
          <Typography variant="subtitle2">{t('meetings.resolutions')}</Typography>
          {resolutions.map((r, i) => (
            <Stack key={i} direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" sx={{ width: 20 }}>{i + 1}.</Typography>
              <TextField size="small" label={t('meetings.resolution')} value={r.text} sx={{ flexGrow: 1 }}
                onChange={(e) => setForm({ ...form, resolutions: resolutions.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} />
              <TextField select size="small" label={t('meetings.decisionLabel')} value={r.decision} sx={{ width: 150 }}
                onChange={(e) => setForm({ ...form, resolutions: resolutions.map((x, j) => (j === i ? { ...x, decision: e.target.value as typeof r.decision } : x)) })}>
                {(['PASSED', 'DEFERRED', 'REJECTED'] as const).map((d) => <MenuItem key={d} value={d}>{t(`meetings.decision.${d}`)}</MenuItem>)}
              </TextField>
              <IconButton aria-label={t('common.remove')} onClick={() => setForm({ ...form, resolutions: resolutions.filter((_, j) => j !== i) })}><DeleteIcon /></IconButton>
            </Stack>
          ))}
          <div><Button size="small" startIcon={<AddIcon />} onClick={() => setForm({ ...form, resolutions: [...resolutions, { text: '', decision: 'PASSED' }] })}>{t('meetings.addResolution')}</Button></div>
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button onClick={() => setEditing(false)}>{t('common.cancel')}</Button>
            <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>{t('meetings.saveMinutes')}</Button>
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

async function downloadPdf(meeting: Meeting) {
  const res = await api.get(`/meetings/${meeting.id}/minutes.pdf`, { responseType: 'blob' });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `minutes-${meeting.code}.pdf`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ----------------------------------------------------------------------------- page
export function MeetingDetailPage() {
  const { meetingId = '' } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const setMeeting = useSetMeeting();
  const { toast, toastError, confirm } = useFeedback();
  const { data: m, isError } = useMeeting(meetingId);
  const [tab, setTab] = useState('overview');
  const [editing, setEditing] = useState(false);
  const cancel = useMutation({
    mutationFn: async (reason: string | null) => (await api.post<Meeting>(`/meetings/${meetingId}/cancel`, { reason })).data,
    onSuccess: (x) => { setMeeting(x); toast(t('meetings.cancelled')); },
    onError: toastError,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/meetings/${meetingId}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: actKeys.meetings }); navigate('/meetings', { replace: true }); },
    onError: toastError,
  });
  if (isError) return <EmptyState title={t('meetings.notFound')} />;
  if (!m) return <Skeleton variant="rounded" height={480} />;
  return (
    <>
      <PageHeader
        title={m.title}
        subtitle={`${m.code} · ${m.org_unit?.name ?? t('activities.parishLevel')} · ${formatWallTime(m.scheduled_at)}`}
        breadcrumbs={[{ label: t('nav.activities') }, { label: t('nav.meetings'), to: '/meetings' }, { label: m.code }]}
        actions={
          <Stack direction="row" spacing={1}>
            {m.can.delete && <Button color="error" onClick={async () => { if (await confirm({ title: t('meetings.deleteConfirm'), destructive: true })) remove.mutate(); }}>{t('common.delete')}</Button>}
            {m.can.cancel && <Button color="inherit" onClick={async () => { if (await confirm({ title: t('meetings.cancelConfirm'), message: t('meetings.cancelHint'), destructive: true })) cancel.mutate(null); }}>{t('meetings.cancel')}</Button>}
            {m.can.edit && <Button startIcon={<EditIcon />} onClick={() => setEditing(true)}>{t('common.edit')}</Button>}
          </Stack>
        }
      />
      {m.status === 'CANCELLED' && <Alert severity="warning" sx={{ mb: 2 }}>{t('meetings.cancelledBanner')}{m.cancel_reason ? ` ${m.cancel_reason}` : ''}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }} variant="scrollable" allowScrollButtonsMobile>
            <Tab value="overview" label={t('meetings.overview')} />
            <Tab value="attendance" label={t('meetings.attendance')} />
            <Tab value="minutes" label={t('meetings.minutes')} />
            <Tab value="actions" label={m.open_actions ? `${t('nav.actionItems')} (${m.open_actions})` : t('nav.actionItems')} />
          </Tabs>
          {tab === 'overview' && (
            <Card>
              <CardHeader title={t('meetings.details')} action={<StatusBadge status={m.status} />} />
              <CardContent sx={{ pt: 0 }}>
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid size={{ xs: 12, sm: 6 }}><Fact label={t('meetings.when')}>{formatWallTime(m.scheduled_at)}{m.ends_at ? ` – ${formatWallTime(m.ends_at, false)}` : ''}</Fact></Grid>
                  <Grid size={{ xs: 12, sm: 6 }}><Fact label={t('activities.location')}>{m.location}</Fact></Grid>
                  <Grid size={{ xs: 12, sm: 6 }}><Fact label={t('meetings.type')}>{t(`meetings.types.${m.meeting_type}`)}</Fact></Grid>
                  <Grid size={{ xs: 12, sm: 6 }}><Fact label={t('meetings.calledBy')}>{m.called_by}</Fact></Grid>
                  {m.description && <Grid size={12}><Fact label={t('common.description')}>{m.description}</Fact></Grid>}
                </Grid>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>{t('meetings.agenda')}</Typography>
                {m.agenda.length === 0 ? <Typography variant="body2" color="text.secondary">—</Typography> : (
                  <Stack component="ol" spacing={0.75} sx={{ pl: 2.5, m: 0 }} aria-label={t('meetings.agenda')}>
                    {m.agenda.map((a) => <li key={a.seq}><Typography variant="body2">{a.title}{a.presenter && <Typography component="span" variant="body2" color="text.secondary"> — {a.presenter}</Typography>}</Typography></li>)}
                  </Stack>
                )}
              </CardContent>
            </Card>
          )}
          {tab === 'attendance' && <AttendanceTab meeting={m} />}
          {tab === 'minutes' && <MinutesTab meeting={m} />}
          {tab === 'actions' && <ActionItemsCard meetingId={m.id} canAdd={m.can.attach} />}
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Stack spacing={2}>
            {m.minutes && <ApprovalSection entityType="MEETING_MINUTES" entityId={m.minutes.id} onChange={() => void qc.invalidateQueries({ queryKey: actKeys.meetings })} />}
            <AttachmentsCard base={`/meetings/${m.id}`} canAdd={m.can.attach} canRemove={m.can.edit} />
          </Stack>
        </Grid>
      </Grid>
      <MeetingDialog open={editing} onClose={() => setEditing(false)} meeting={m} />
    </>
  );
}
