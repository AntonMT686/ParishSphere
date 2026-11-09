import { zodResolver } from '@hookform/resolvers/zod';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { api } from '@/api/client';
import type { UserOut } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { applyServerErrors, FormSelect, FormTextField, useFeedback } from '@/design-system';
import { useRoles } from './api';

const schema = z
  .object({
    username: z.string().trim().min(3, 'At least 3 characters').max(100).regex(/^[A-Za-z0-9._-]+$/, 'Letters, digits, . _ - only'),
    full_name: z.string().trim().min(2, 'Required').max(200),
    email: z.union([z.literal(''), z.string().trim().email('Invalid email')]),
    phone: z.string().trim().max(30),
    preferred_language: z.enum(['en', 'ta']),
    password: z.string().max(256),
    role_codes: z.array(z.string()),
  })
  .refine((v) => v.password || v.email, { path: ['email'], message: 'Email is required to send an invitation' });
type Values = z.infer<typeof schema>;
const FIELDS = ['username', 'full_name', 'email', 'phone', 'password', 'role_codes'] as const;

export function CreateUserDialog({ open, onClose, onCreated }: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError } = useFeedback();
  const { data: roles } = useRoles(open);
  const parishRoles = (roles ?? []).filter((r) => r.scope_type !== 'ORG_UNIT');
  const { control, handleSubmit, reset, setError, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', full_name: '', email: '', phone: '', preferred_language: 'en', password: '', role_codes: [] },
  });
  const create = useMutation({
    mutationFn: async (v: Values) =>
      (
        await api.post<UserOut>('/users', {
          ...v,
          email: v.email || null,
          phone: v.phone || null,
          password: v.password || null,
        })
      ).data,
    onSuccess: (u) => {
      void qc.invalidateQueries({ queryKey: ['users'] });
      toast(t('common.saved'));
      reset();
      onClose();
      onCreated(u.id);
    },
    onError: (e) => {
      if (!applyServerErrors(e, setError, FIELDS)) toastError(e);
    },
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <form noValidate onSubmit={handleSubmit((v) => create.mutate(v))}>
        <DialogTitle>{t('users.new')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <FormTextField control={control} name="full_name" label={t('users.fullName')} autoFocus required />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormTextField control={control} name="username" label={t('common.username')} required />
              <FormSelect control={control} name="preferred_language" label={t('common.language')}
                options={[{ value: 'en', label: 'English' }, { value: 'ta', label: 'தமிழ்' }]} />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <FormTextField control={control} name="email" label={t('common.email')} type="email" />
              <FormTextField control={control} name="phone" label={t('common.phone')} />
            </Stack>
            <FormTextField control={control} name="password" label={t('users.initialPassword')} type="password"
              helperText={t('users.inviteHint')} autoComplete="new-password" />
            {can('user.assign_role') && (
              <Controller
                control={control}
                name="role_codes"
                render={({ field }) => (
                  <Autocomplete
                    multiple
                    options={parishRoles.map((r) => r.code)}
                    getOptionLabel={(c) => parishRoles.find((r) => r.code === c)?.name ?? c}
                    value={field.value}
                    onChange={(_, v) => field.onChange(v)}
                    renderInput={(p) => <TextField {...p} label={t('common.roles')} />}
                  />
                )}
              />
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" variant="contained" disabled={formState.isSubmitting || create.isPending}>
            {t('common.create')}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  );
}
