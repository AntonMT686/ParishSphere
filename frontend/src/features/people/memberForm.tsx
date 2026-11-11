import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Typography from '@mui/material/Typography';
import type { Control, FieldValues, Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { FormSelect, FormTextField } from '@/design-system';
import { GENDERS, MARITAL, RELATIONSHIPS, useLabels } from './labels';

const optText = (max: number) => z.string().trim().max(max);
const optDate = z.string().refine((v) => !v || !Number.isNaN(Date.parse(v)), 'Invalid date');

export const memberSchema = z.object({
  first_name: z.string().trim().min(1, 'Required').max(100),
  last_name: optText(100),
  name_local: optText(200),
  gender: z.enum(GENDERS, { message: 'Required' }),
  date_of_birth: optDate,
  relationship_to_head: z.enum(RELATIONSHIPS),
  phone: optText(30),
  email: z.union([z.literal(''), z.string().trim().email('Invalid email')]),
  education: optText(200),
  occupation: optText(200),
  marital_status: z.union([z.literal(''), z.enum(MARITAL)]),
  baptism_date: optDate,
  baptism_place: optText(200),
  baptism_register_ref: optText(50),
  communion_date: optDate,
  communion_place: optText(200),
  confirmation_date: optDate,
  confirmation_place: optText(200),
  marriage_date: optDate,
  marriage_place: optText(200),
  marriage_register_ref: optText(50),
  remarks: optText(2000),
});
export type MemberValues = z.infer<typeof memberSchema>;
export const MEMBER_FIELDS = Object.keys(memberSchema.shape);
export const SACRAMENT_KEYS = [
  'baptism_date', 'baptism_place', 'baptism_register_ref', 'communion_date', 'communion_place', 'confirmation_date',
  'confirmation_place', 'marriage_date', 'marriage_place', 'marriage_register_ref',
] as const;
export const SENSITIVE_KEYS = ['date_of_birth', 'phone', 'email', 'education', 'occupation', 'marital_status', 'remarks'] as const;

export function emptyMember(rel: MemberValues['relationship_to_head'] = 'OTHER'): MemberValues {
  const blank = Object.fromEntries(MEMBER_FIELDS.map((k) => [k, ''])) as unknown as MemberValues;
  return { ...blank, relationship_to_head: rel, gender: '' as unknown as MemberValues['gender'] };
}

/** Convert form values ('' for empty) to the API shape (null for empty). */
export function toApi(v: Partial<MemberValues>, opts: { sensitive: boolean; sacraments: boolean }) {
  const out: Record<string, unknown> = {};
  for (const [k, val] of Object.entries(v)) {
    if (!opts.sacraments && (SACRAMENT_KEYS as readonly string[]).includes(k)) continue;
    if (!opts.sensitive && (SENSITIVE_KEYS as readonly string[]).includes(k)) continue;
    out[k] = val === '' ? null : val;
  }
  return out;
}

export function MemberFormFields<T extends FieldValues>({ control, base, sensitive, sacraments, headLocked }: {
  control: Control<T>;
  base: string;
  sensitive: boolean;
  sacraments: boolean;
  headLocked?: boolean;
}) {
  const { t } = useTranslation();
  const L = useLabels();
  const n = (k: string) => (base ? `${base}.${k}` : k) as Path<T>;
  const date = { type: 'date', slotProps: { inputLabel: { shrink: true } } } as const;
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('first_name')} label={t('people.firstName')} required /></Grid>
      <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('last_name')} label={t('people.lastName')} /></Grid>
      <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('name_local')} label={t('people.nameLocal')} /></Grid>
      <Grid size={{ xs: 12, sm: 4 }}>
        <FormSelect control={control} name={n('gender')} label={t('people.genderLabel')} required
          options={GENDERS.map((g) => ({ value: g, label: L.gender(g) }))} />
      </Grid>
      <Grid size={{ xs: 12, sm: 4 }}>
        <FormSelect control={control} name={n('relationship_to_head')} label={t('people.relationship')} disabled={headLocked}
          options={RELATIONSHIPS.map((r) => ({ value: r, label: L.rel(r) }))} />
      </Grid>
      {sensitive && (
        <>
          <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('date_of_birth')} label={t('people.dob')} {...date} /></Grid>
          <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('phone')} label={t('common.phone')} /></Grid>
          <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n('email')} label={t('common.email')} /></Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <FormSelect control={control} name={n('marital_status')} label={t('people.maritalStatus')}
              options={[{ value: '', label: '—' }, ...MARITAL.map((m) => ({ value: m, label: L.marital(m) }))]} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}><FormTextField control={control} name={n('education')} label={t('people.education')} /></Grid>
          <Grid size={{ xs: 12, sm: 6 }}><FormTextField control={control} name={n('occupation')} label={t('people.occupation')} /></Grid>
        </>
      )}
      {sacraments && (
        <>
          <Grid size={12}><Divider><Typography variant="caption" color="text.secondary">{t('people.sacraments')}</Typography></Divider></Grid>
          {(['baptism', 'communion', 'confirmation', 'marriage'] as const).map((s) => (
            <Grid key={s} size={12} container spacing={2}>
              <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n(`${s}_date`)} label={t(`people.${s}Date`)} {...date} /></Grid>
              <Grid size={{ xs: 12, sm: s === 'baptism' || s === 'marriage' ? 4 : 8 }}>
                <FormTextField control={control} name={n(`${s}_place`)} label={t('people.place')} />
              </Grid>
              {(s === 'baptism' || s === 'marriage') && (
                <Grid size={{ xs: 12, sm: 4 }}><FormTextField control={control} name={n(`${s}_register_ref`)} label={t('people.registerRef')} /></Grid>
              )}
            </Grid>
          ))}
        </>
      )}
      {sensitive && (
        <Grid size={12}><FormTextField control={control} name={n('remarks')} label={t('people.remarks')} multiline minRows={2} /></Grid>
      )}
    </Grid>
  );
}
