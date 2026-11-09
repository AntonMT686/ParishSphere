import { zodResolver } from '@hookform/resolvers/zod';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { api } from '@/api/client';
import type { OrgUnit, OrgUnitType } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { applyServerErrors, FormTextField, useFeedback } from '@/design-system';
import { orgKeys } from './api';
import { OrgUnitPicker } from './pickers';

const opt = (max: number) => z.string().trim().max(max);
const schema = z.object({
  name: z.string().trim().min(2, 'Required').max(200),
  name_local: opt(200),
  code: z.union([z.literal(''), z.string().trim().max(30).regex(/^[A-Za-z0-9_-]+$/, 'Letters, digits, - and _')]),
  description: opt(5000),
  established_on: z.string(),
  meeting_place: opt(255),
  meeting_schedule: opt(255),
  contact_phone: opt(30),
  contact_email: z.union([z.literal(''), z.string().trim().email('Invalid email')]),
});
type Values = z.infer<typeof schema>;
const FIELDS = Object.keys(schema.shape);

function nullify(v: Values) {
  return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === '' ? null : x]));
}

/** Create (with `type`) or edit (with `unit`) an organisation unit. */
export function OrgUnitDialog({ open, onClose, type, unit, defaultParent, onSaved }: {
  open: boolean;
  onClose: () => void;
  type: Pick<OrgUnitType, 'code' | 'name'>;
  unit?: OrgUnit;
  defaultParent?: Pick<OrgUnit, 'id' | 'name' | 'code'> | null;
  onSaved?: (u: OrgUnit) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError } = useFeedback();
  const [parent, setParent] = useState<Pick<OrgUnit, 'id' | 'name' | 'code'> | null>(null);
  const { control, handleSubmit, reset, setError } = useForm<Values>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (!open) return;
    reset({
      name: unit?.name ?? '', name_local: unit?.name_local ?? '', code: unit?.code ?? '',
      description: unit?.description ?? '', established_on: unit?.established_on ?? '',
      meeting_place: unit?.meeting_place ?? '', meeting_schedule: unit?.meeting_schedule ?? '',
      contact_phone: unit?.contact_phone ?? '', contact_email: unit?.contact_email ?? '',
    });
    setParent(unit?.parent ?? defaultParent ?? null);
  }, [open, unit, defaultParent, reset]);

  const save = useMutation({
    mutationFn: async (v: Values) => {
      const body = nullify(v);
      if (unit) {
        delete body.code;
        if (can('org_unit.create') && (parent?.id ?? null) !== (unit.parent?.id ?? null)) body.parent_id = parent?.id ?? '';
        return (await api.patch<OrgUnit>(`/org-units/${unit.id}`, body)).data;
      }
      return (await api.post<OrgUnit>('/org-units', { ...body, type_code: type.code, parent_id: parent?.id ?? null })).data;
    },
    onSuccess: (u) => {
      void qc.invalidateQueries({ queryKey: orgKeys.units });
      void qc.invalidateQueries({ queryKey: orgKeys.types });
      toast(t('common.saved'));
      onClose();
      onSaved?.(u);
    },
    onError: (e) => {
      if (!applyServerErrors(e, setError, FIELDS)) toastError(e);
    },
  });

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form noValidate onSubmit={handleSubmit((v) => save.mutate(v))}>
        <DialogTitle>{unit ? `${t('common.edit')}: ${unit.name}` : t('org.newUnit', { type: type.name })}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <FormTextField control={control} name="name" label={t('common.name')} required autoFocus />
            <FormTextField control={control} name="name_local" label={t('org.nameLocal')} />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormTextField control={control} name="code" label={t('org.code')} disabled={Boolean(unit)}
                helperText={unit ? undefined : t('org.codeHint')} />
              <FormTextField control={control} name="established_on" label={t('org.established')} type="date"
                slotProps={{ inputLabel: { shrink: true } }} />
            </Stack>
            {(!unit || can('org_unit.create')) && (
              <OrgUnitPicker label={t('org.parent')} value={parent} onChange={setParent} excludeId={unit?.id} />
            )}
            <FormTextField control={control} name="description" label={t('roles.description')} multiline minRows={2} />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormTextField control={control} name="meeting_place" label={t('org.meetingPlace')} />
              <FormTextField control={control} name="meeting_schedule" label={t('org.meetingSchedule')}
                placeholder={t('org.meetingScheduleHint')} />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormTextField control={control} name="contact_phone" label={t('common.phone')} />
              <FormTextField control={control} name="contact_email" label={t('common.email')} type="email" />
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={save.isPending}>
            {unit ? t('common.save') : t('common.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
