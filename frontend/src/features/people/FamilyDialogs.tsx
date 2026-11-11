import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import type { Family, FamilyListItem } from '@/api/types';
import { useFeedback } from '@/design-system';
import { OrgUnitPicker } from '@/features/org/pickers';
import { peopleKeys } from './api';
import { RELATIONSHIPS, useLabels } from './labels';
import { FamilyPicker } from './pickers';

export type FamilyAction = 'edit' | 'anbiyam' | 'head' | 'transfer' | 'merge' | 'split' | null;

function useFamilyMutation(familyId: string, onDone: (f: Family) => void) {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const { toast, toastError } = useFeedback();
  return useMutation({
    mutationFn: async ({ path, body, method = 'post' }: { path: string; body: unknown; method?: 'post' | 'patch' }) =>
      (await api.request<Family>({ url: `/families/${familyId}${path}`, method, data: body })).data,
    onSuccess: (f) => {
      void qc.invalidateQueries({ queryKey: peopleKeys.families });
      void qc.invalidateQueries({ queryKey: peopleKeys.members });
      toast(t('common.saved'));
      onDone(f);
    },
    onError: toastError,
  });
}

function Shell({ open, title, onClose, onSubmit, disabled, children, submitLabel, destructive }: {
  open: boolean; title: string; onClose: () => void; onSubmit: () => void; disabled?: boolean; children: ReactNode;
  submitLabel?: string; destructive?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt: 1 }}>{children}</Stack></DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" color={destructive ? 'error' : 'primary'} onClick={onSubmit} disabled={disabled}>
          {submitLabel ?? t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

const today = () => new Date().toISOString().slice(0, 10);

export function FamilyDialogs({ family, action, onClose }: { family: Family; action: FamilyAction; onClose: () => void }) {
  const { t } = useTranslation();
  const L = useLabels();
  const navigate = useNavigate();
  const m = useFamilyMutation(family.id, (f) => {
    onClose();
    if (f.id !== family.id) navigate(`/families/${f.id}`);
  });
  const active = family.members.filter((x) => x.status === 'ACTIVE');
  // shared state
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [unit, setUnit] = useState<{ id: string; name: string; code: string } | null>(null);
  const [date, setDate] = useState(today());
  const [reason, setReason] = useState('');
  const [head, setHead] = useState('');
  const [prevRel, setPrevRel] = useState('OTHER');
  const [toParish, setToParish] = useState('');
  const [toDiocese, setToDiocese] = useState('');
  const [target, setTarget] = useState<FamilyListItem | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [newName, setNewName] = useState('');
  const [remainingHead, setRemainingHead] = useState('');

  useEffect(() => {
    if (!action) return;
    setDate(today()); setReason(''); setHead(''); setPrevRel('OTHER'); setToParish(''); setToDiocese('');
    setTarget(null); setSelected([]); setNewName(''); setRemainingHead('');
    setUnit(family.anbiyam ? { ...family.anbiyam } : null);
    setEdit(Object.fromEntries(['family_name', 'family_name_local', 'phone', 'email', 'address_line1', 'address_line2', 'city', 'state', 'postal_code', 'previous_parish', 'previous_diocese', 'remarks']
      .map((k) => [k, ((family as unknown as Record<string, string | null>)[k]) ?? ''])));
  }, [action, family]);

  const field = (k: string, label: string, props: object = {}) => (
    <TextField label={label} value={edit[k] ?? ''} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} {...props} />
  );
  const common = (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      <TextField label={t('people.effectiveDate')} type="date" value={date} onChange={(e) => setDate(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
      <TextField label={t('people.reason')} value={reason} onChange={(e) => setReason(e.target.value)} />
    </Stack>
  );
  const headLeaves = family.head_member_id !== null && selected.includes(family.head_member_id);
  const remaining = active.filter((x) => !selected.includes(x.id));

  return (
    <>
      <Shell open={action === 'edit'} title={`${t('common.edit')}: ${family.family_name}`} onClose={onClose}
        onSubmit={() => m.mutate({ path: '', method: 'patch', body: Object.fromEntries(Object.entries(edit).map(([k, v]) => [k, v === '' ? null : v])) })}
        disabled={!edit.family_name || m.isPending}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 6 }}>{field('family_name', t('people.familyName'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{field('family_name_local', t('people.familyNameLocal'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{field('phone', t('common.phone'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{field('email', t('common.email'))}</Grid>
          <Grid size={12}>{field('address_line1', t('people.address1'))}</Grid>
          <Grid size={12}>{field('address_line2', t('people.address2'))}</Grid>
          <Grid size={{ xs: 12, sm: 5 }}>{field('city', t('people.city'))}</Grid>
          <Grid size={{ xs: 12, sm: 4 }}>{field('state', t('people.state'))}</Grid>
          <Grid size={{ xs: 12, sm: 3 }}>{field('postal_code', t('people.postalCode'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{field('previous_parish', t('people.previousParish'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{field('previous_diocese', t('people.previousDiocese'))}</Grid>
          <Grid size={12}>{field('remarks', t('people.remarks'), { multiline: true, minRows: 2 })}</Grid>
        </Grid>
      </Shell>

      <Shell open={action === 'anbiyam'} title={t('people.changeAnbiyam')} onClose={onClose} disabled={m.isPending}
        onSubmit={() => m.mutate({ path: '/anbiyam', body: { anbiyam_id: unit?.id ?? null, effective_date: date, reason: reason || null } })}>
        <OrgUnitPicker label={t('nav.anbiyam')} type="ANBIYAM" value={unit} onChange={setUnit} />
        {common}
      </Shell>

      <Shell open={action === 'head'} title={t('people.setHead')} onClose={onClose} disabled={!head || m.isPending}
        onSubmit={() => m.mutate({ path: '/head', body: { member_id: head, previous_head_relationship: prevRel } })}>
        <TextField select label={t('people.newHead')} value={head} onChange={(e) => setHead(e.target.value)}>
          {active.filter((x) => !x.is_head).map((x) => <MenuItem key={x.id} value={x.id}>{x.full_name} · {L.rel(x.relationship_to_head)}</MenuItem>)}
        </TextField>
        {family.members.some((x) => x.relationship_to_head === 'HEAD') && (
          <TextField select label={t('people.previousHeadBecomes')} value={prevRel} onChange={(e) => setPrevRel(e.target.value)}>
            {RELATIONSHIPS.filter((r) => r !== 'HEAD').map((r) => <MenuItem key={r} value={r}>{L.rel(r)}</MenuItem>)}
          </TextField>
        )}
        <Alert severity="info">{t('people.relationshipsHint')}</Alert>
      </Shell>

      <Shell open={action === 'transfer'} title={t('people.transferOut')} onClose={onClose} destructive disabled={toParish.trim().length < 2 || m.isPending}
        submitLabel={t('people.transferOut')}
        onSubmit={() => m.mutate({ path: '/transfer-out', body: { to_parish: toParish, to_diocese: toDiocese || null, effective_date: date, reason: reason || null } })}>
        <Alert severity="warning">{t('people.transferWarning')}</Alert>
        <TextField label={t('people.toParish')} value={toParish} onChange={(e) => setToParish(e.target.value)} required />
        <TextField label={t('people.toDiocese')} value={toDiocese} onChange={(e) => setToDiocese(e.target.value)} />
        {common}
      </Shell>

      <Shell open={action === 'merge'} title={t('people.merge')} onClose={onClose} destructive disabled={!target || m.isPending}
        submitLabel={t('people.merge')}
        onSubmit={() => m.mutate({ path: '/merge', body: { into_family_id: target?.id, effective_date: date, reason: reason || null } })}>
        <Alert severity="warning">{t('people.mergeWarning', { family: family.family_name })}</Alert>
        <FamilyPicker label={t('people.mergeInto')} value={target} onChange={setTarget} excludeId={family.id} />
        {common}
      </Shell>

      <Shell open={action === 'split'} title={t('people.split')} onClose={onClose}
        disabled={!selected.length || !head || !newName.trim() || (headLeaves && remaining.length > 0 && !remainingHead) || m.isPending}
        submitLabel={t('people.split')}
        onSubmit={() => m.mutate({ path: '/split', body: {
          member_ids: selected, head_member_id: head, remaining_head_member_id: remainingHead || null,
          new_family: { family_name: newName }, anbiyam_id: unit?.id ?? null, effective_date: date, reason: reason || null,
        } })}>
        <TextField label={t('people.newFamilyName')} value={newName} onChange={(e) => setNewName(e.target.value)} required />
        <FormGroup>
          {active.map((x) => (
            <FormControlLabel key={x.id} label={`${x.full_name} · ${L.rel(x.relationship_to_head)}`}
              control={<Checkbox checked={selected.includes(x.id)} onChange={(_, v) => {
                setSelected(v ? [...selected, x.id] : selected.filter((s) => s !== x.id));
                if (!v && head === x.id) setHead('');
              }} />} />
          ))}
        </FormGroup>
        <TextField select label={t('people.newFamilyHead')} value={head} onChange={(e) => setHead(e.target.value)} disabled={!selected.length}>
          {active.filter((x) => selected.includes(x.id)).map((x) => <MenuItem key={x.id} value={x.id}>{x.full_name}</MenuItem>)}
        </TextField>
        {headLeaves && remaining.length > 0 && (
          <TextField select label={t('people.remainingHead')} value={remainingHead} onChange={(e) => setRemainingHead(e.target.value)}>
            {remaining.map((x) => <MenuItem key={x.id} value={x.id}>{x.full_name}</MenuItem>)}
          </TextField>
        )}
        <OrgUnitPicker label={t('people.newFamilyAnbiyam')} type="ANBIYAM" value={unit} onChange={setUnit} />
        {common}
      </Shell>
    </>
  );
}
