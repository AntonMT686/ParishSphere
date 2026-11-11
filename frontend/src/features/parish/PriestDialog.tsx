import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { Priest } from '@/api/types';
import { useFeedback } from '@/design-system';
import { parishKeys } from './api';

const FIELDS = ['title', 'full_name', 'name_local', 'date_of_birth', 'ordination_date', 'clergy_type', 'home_diocese',
  'congregation', 'phone', 'email', 'remarks'] as const;
type Form = Record<(typeof FIELDS)[number], string>;
const EMPTY: Form = { title: 'Rev. Fr.', full_name: '', name_local: '', date_of_birth: '', ordination_date: '', clergy_type: 'DIOCESAN',
  home_diocese: '', congregation: '', phone: '', email: '', remarks: '' };

/** Create a priest (``priest`` undefined) or edit one. */
export function PriestDialog({ open, onClose, priest, onCreated }: {
  open: boolean; onClose: () => void; priest?: Priest; onCreated?: (p: Priest) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [form, setForm] = useState<Form>(EMPTY);
  useEffect(() => {
    if (open) setForm(priest ? Object.fromEntries(FIELDS.map((k) => [k, priest[k] ?? ''])) as Form : EMPTY);
  }, [open, priest]);
  const save = useMutation({
    mutationFn: async () => {
      const body = Object.fromEntries(FIELDS.map((k) => [k, form[k].trim() === '' ? null : form[k].trim()]));
      body.title ??= 'Rev. Fr.';
      return priest
        ? (await api.patch<Priest>(`/priests/${priest.id}`, body)).data
        : (await api.post<Priest>('/priests', body)).data;
    },
    onSuccess: (p) => {
      void qc.invalidateQueries({ queryKey: parishKeys.priests });
      void qc.invalidateQueries({ queryKey: parishKeys.clergy });
      toast(t('common.saved'));
      onClose();
      if (!priest) onCreated?.(p);
    },
    onError: toastError,
  });
  const f = (k: keyof Form, label: string, props: object = {}) => (
    <TextField label={label} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} {...props} />
  );
  const date = { type: 'date', slotProps: { inputLabel: { shrink: true } } };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{priest ? t('priests.edit') : t('priests.add')}</DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ pt: 1 }}>
          <Grid size={{ xs: 12, sm: 4 }}>{f('title', t('priests.title'))}</Grid>
          <Grid size={{ xs: 12, sm: 8 }}>{f('full_name', t('common.name'), { required: true, autoFocus: true })}</Grid>
          <Grid size={12}>{f('name_local', t('parish.nameLocal'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{f('date_of_birth', t('people.dob'), date)}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{f('ordination_date', t('priests.ordination'), date)}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            {f('clergy_type', t('priests.clergyType'), { select: true, children: ['DIOCESAN', 'RELIGIOUS'].map((c) => (
              <MenuItem key={c} value={c}>{t(`priests.clergy.${c}`)}</MenuItem>)) })}
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            {form.clergy_type === 'RELIGIOUS' ? f('congregation', t('priests.congregation')) : f('home_diocese', t('priests.homeDiocese'))}
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{f('phone', t('common.phone'))}</Grid>
          <Grid size={{ xs: 12, sm: 6 }}>{f('email', t('common.email'))}</Grid>
          <Grid size={12}>{f('remarks', t('common.remarks'), { multiline: true, minRows: 2 })}</Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={form.full_name.trim().length < 2 || save.isPending} onClick={() => save.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}
