import { zodResolver } from '@hookform/resolvers/zod';
import AddIcon from '@mui/icons-material/PersonAddAlt1Outlined';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import WarningIcon from '@mui/icons-material/WarningAmberOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Radio from '@mui/material/Radio';
import Stack from '@mui/material/Stack';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { api } from '@/api/client';
import type { DuplicateCandidate, Family } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { FormTextField, PageHeader, useFeedback } from '@/design-system';
import { OrgUnitPicker } from '@/features/org/pickers';
import { peopleKeys } from './api';
import { useLabels } from './labels';
import { emptyMember, MemberFormFields, memberSchema, toApi } from './memberForm';

const opt = (max: number) => z.string().trim().max(max);
const schema = z.object({
  family_name: z.string().trim().min(1, 'Required').max(200),
  family_name_local: opt(200),
  phone: opt(30),
  email: z.union([z.literal(''), z.string().trim().email('Invalid email')]),
  registered_on: z.string(),
  previous_parish: opt(200),
  previous_diocese: opt(200),
  address_line1: opt(255),
  address_line2: opt(255),
  city: opt(100),
  state: opt(100),
  postal_code: opt(20),
  remarks: opt(2000),
  members: z.array(memberSchema).min(1),
});
type Values = z.infer<typeof schema>;
const STEP_FIELDS: (keyof Values)[][] = [
  ['family_name', 'family_name_local', 'phone', 'email', 'registered_on', 'previous_parish', 'previous_diocese'],
  ['address_line1', 'address_line2', 'city', 'state', 'postal_code'],
  ['members'],
  [],
];

export function RegisterFamilyPage() {
  const { t } = useTranslation();
  const L = useLabels();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useCan();
  const { toastError } = useFeedback();
  const sacraments = can('sacrament.update');
  const [step, setStep] = useState(0);
  const [anbiyam, setAnbiyam] = useState<{ id: string; name: string; code: string } | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateCandidate[] | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const { control, handleSubmit, trigger, getValues, setValue, watch } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      family_name: '', family_name_local: '', phone: '', email: '', registered_on: new Date().toISOString().slice(0, 10),
      previous_parish: '', previous_diocese: '', address_line1: '', address_line2: '', city: '', state: '',
      postal_code: '', remarks: '', members: [emptyMember('HEAD')],
    },
  });
  const { fields, append, remove } = useFieldArray({ control, name: 'members' });
  const members = watch('members');
  const headIndex = members.findIndex((m) => m.relationship_to_head === 'HEAD');
  const steps = [t('people.stepFamily'), t('people.stepAddress'), t('people.stepMembers'), t('people.stepReview')];

  const makeHead = (i: number) => {
    members.forEach((m, j) => {
      if (j === i) setValue(`members.${j}.relationship_to_head`, 'HEAD');
      else if (m.relationship_to_head === 'HEAD') setValue(`members.${j}.relationship_to_head`, 'OTHER');
    });
  };

  const body = (v: Values): Record<string, unknown> & { members: Record<string, unknown>[] } => ({
    ...Object.fromEntries(Object.entries(v).filter(([k]) => k !== 'members').map(([k, x]) => [k, x === '' ? null : x])),
    anbiyam_id: anbiyam?.id ?? null,
    members: v.members.map((m) => toApi(m, { sensitive: true, sacraments })),
  });

  const checkDuplicates = useMutation({
    mutationFn: async (v: Values) => {
      const b = body(v);
      return (await api.post<DuplicateCandidate[]>('/families/check-duplicates', { family_name: b.family_name, phone: b.phone, members: b.members })).data;
    },
    onSuccess: (d) => { setDuplicates(d); setConfirmed(false); },
    onError: toastError,
  });
  const create = useMutation({
    mutationFn: async (v: Values) => (await api.post<Family>('/families', { ...body(v), confirm_not_duplicate: confirmed })).data,
    onSuccess: (f) => {
      void qc.invalidateQueries({ queryKey: peopleKeys.families });
      navigate(`/families/${f.id}`, { replace: true });
    },
    onError: toastError,
  });

  const next = async () => {
    const ok = await trigger(STEP_FIELDS[step] as (keyof Values)[]);
    if (step === 2 && headIndex < 0) return;
    if (!ok) return;
    if (step === 2) checkDuplicates.mutate(getValues());
    setStep((s) => s + 1);
  };

  return (
    <>
      <PageHeader title={t('people.register')} breadcrumbs={[{ label: t('nav.families'), to: '/families' }, { label: t('people.register') }]} />
      <Stepper activeStep={step} alternativeLabel sx={{ mb: 3 }}>
        {steps.map((s) => (<Step key={s}><StepLabel>{s}</StepLabel></Step>))}
      </Stepper>
      <Box component="form" noValidate onSubmit={handleSubmit((v) => create.mutate(v))}>
        <Card><CardContent>
          {step === 0 && (
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}><FormTextField control={control} name="family_name" label={t('people.familyName')} required autoFocus /></Grid>
              <Grid size={{ xs: 12, md: 6 }}><FormTextField control={control} name="family_name_local" label={t('people.familyNameLocal')} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><FormTextField control={control} name="phone" label={t('common.phone')} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><FormTextField control={control} name="email" label={t('common.email')} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><FormTextField control={control} name="registered_on" label={t('people.registered')} type="date" slotProps={{ inputLabel: { shrink: true } }} /></Grid>
              <Grid size={{ xs: 12, md: 6 }}><FormTextField control={control} name="previous_parish" label={t('people.previousParish')} /></Grid>
              <Grid size={{ xs: 12, md: 6 }}><FormTextField control={control} name="previous_diocese" label={t('people.previousDiocese')} /></Grid>
            </Grid>
          )}
          {step === 1 && (
            <Grid container spacing={2}>
              <Grid size={12}><FormTextField control={control} name="address_line1" label={t('people.address1')} autoFocus /></Grid>
              <Grid size={12}><FormTextField control={control} name="address_line2" label={t('people.address2')} /></Grid>
              <Grid size={{ xs: 12, md: 5 }}><FormTextField control={control} name="city" label={t('people.city')} /></Grid>
              <Grid size={{ xs: 12, md: 4 }}><FormTextField control={control} name="state" label={t('people.state')} /></Grid>
              <Grid size={{ xs: 12, md: 3 }}><FormTextField control={control} name="postal_code" label={t('people.postalCode')} /></Grid>
            </Grid>
          )}
          {step === 2 && (
            <Stack spacing={2}>
              {headIndex < 0 && <Alert severity="warning">{t('people.chooseHead')}</Alert>}
              {fields.map((f, i) => (
                <Card key={f.id} variant="outlined" sx={{ borderColor: i === headIndex ? 'primary.main' : undefined }}>
                  <CardContent>
                    <Stack direction="row" alignItems="center" sx={{ mb: 1 }}>
                      <Typography variant="h4" sx={{ flexGrow: 1 }}>{t('people.memberN', { n: i + 1 })}</Typography>
                      <FormControlLabel control={<Radio checked={i === headIndex} onChange={() => makeHead(i)} />} label={t('people.head')} />
                      {fields.length > 1 && (
                        <IconButton aria-label={t('common.delete')} onClick={() => remove(i)}><DeleteIcon /></IconButton>
                      )}
                    </Stack>
                    <MemberFormFields control={control} base={`members.${i}`} sensitive sacraments={sacraments} headLocked={i === headIndex} />
                  </CardContent>
                </Card>
              ))}
              <Box><Button startIcon={<AddIcon />} onClick={() => append(emptyMember('SON'))}>{t('people.addMember')}</Button></Box>
            </Stack>
          )}
          {step === 3 && (
            <Stack spacing={2}>
              <OrgUnitPicker label={t('nav.anbiyam')} type="ANBIYAM" value={anbiyam} onChange={setAnbiyam} />
              {!anbiyam && <Alert severity="info">{t('people.pendingAnbiyamHint')}</Alert>}
              <Typography variant="h4">{getValues('family_name')}</Typography>
              <List dense>
                {members.map((m, i) => (
                  <ListItem key={i} disableGutters>
                    <ListItemText primary={`${m.first_name} ${m.last_name}`.trim()} secondary={`${L.rel(m.relationship_to_head)} · ${m.gender ? L.gender(m.gender) : ''}${m.date_of_birth ? ` · ${m.date_of_birth}` : ''}`} />
                  </ListItem>
                ))}
              </List>
              {checkDuplicates.isPending && <Alert severity="info">{t('people.checkingDuplicates')}</Alert>}
              {duplicates && duplicates.length > 0 && (
                <Alert severity="warning" icon={<WarningIcon />}>
                  <Typography fontWeight={600}>{t('people.possibleDuplicates')}</Typography>
                  <List dense>
                    {duplicates.map((d) => (
                      <ListItem key={d.family_id} disableGutters>
                        <ListItemText
                          primary={<Link component={RouterLink} to={`/families/${d.family_id}`} target="_blank">{d.family_code} · {d.family_name}</Link>}
                          secondary={d.reasons.join(' · ')}
                        />
                      </ListItem>
                    ))}
                  </List>
                  <FormControlLabel control={<Checkbox checked={confirmed} onChange={(_, v) => setConfirmed(v)} />} label={t('people.confirmNotDuplicate')} />
                </Alert>
              )}
              {duplicates && duplicates.length === 0 && <Alert severity="success">{t('people.noDuplicates')}</Alert>}
            </Stack>
          )}
        </CardContent></Card>
        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 2 }}>
          <Button component={RouterLink} to="/families">{t('common.cancel')}</Button>
          {step > 0 && <Button onClick={() => setStep((s) => s - 1)}>{t('people.back')}</Button>}
          {step < 3 ? (
            <Button variant="contained" onClick={() => void next()}>{t('people.next')}</Button>
          ) : (
            <Button type="submit" variant="contained" disabled={create.isPending || checkDuplicates.isPending || Boolean(duplicates?.length && !confirmed)}>
              {t('people.registerFamily')}
            </Button>
          )}
        </Stack>
      </Box>
    </>
  );
}
