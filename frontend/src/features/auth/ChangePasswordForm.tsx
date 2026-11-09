import { zodResolver } from '@hookform/resolvers/zod';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { api } from '@/api/client';
import { useAuthStore } from '@/auth/authStore';
import { applyServerErrors, FormTextField, useErrorMessage } from '@/design-system';
import { withConfirm } from './passwordSchema';

export function ChangePasswordForm({ onDone }: { onDone?: () => void }) {
  const { t } = useTranslation();
  const errorMessage = useErrorMessage();
  const reloadMe = useAuthStore((s) => s.reloadMe);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const schema = withConfirm({ current_password: z.string().min(1, 'Required') }, t('auth.passwordsDontMatch'));
  const { control, handleSubmit, formState, setError: setFieldError, reset } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { current_password: '', new_password: '', confirm: '' },
  });
  const onSubmit = async (v: { current_password: string; new_password: string }) => {
    setError(null);
    setSuccess(false);
    try {
      await api.post('/auth/password/change', { current_password: v.current_password, new_password: v.new_password });
      await reloadMe();
      reset();
      setSuccess(true);
      onDone?.();
    } catch (e) {
      if (!applyServerErrors(e, setFieldError, ['current_password', 'new_password'])) setError(errorMessage(e));
    }
  };
  return (
    <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}>
      <Stack spacing={2}>
        {error && <Alert severity="error">{error}</Alert>}
        {success && <Alert severity="success">{t('auth.changeDone')}</Alert>}
        <FormTextField control={control} name="current_password" type="password" label={t('auth.currentPassword')}
          autoComplete="current-password" />
        <FormTextField control={control} name="new_password" type="password" label={t('auth.newPassword')}
          helperText={t('auth.passwordHint')} autoComplete="new-password" />
        <FormTextField control={control} name="confirm" type="password" label={t('auth.confirmPassword')}
          autoComplete="new-password" />
        <Box>
          <Button type="submit" variant="contained" disabled={formState.isSubmitting}>
            {t('auth.changeTitle')}
          </Button>
        </Box>
      </Stack>
    </Box>
  );
}
