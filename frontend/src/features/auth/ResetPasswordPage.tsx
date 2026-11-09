import { zodResolver } from '@hookform/resolvers/zod';
import KeyIcon from '@mui/icons-material/KeyOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { api } from '@/api/client';
import { applyServerErrors, FormTextField, useErrorMessage } from '@/design-system';
import { AuthCard } from './AuthCard';
import { withConfirm } from './passwordSchema';

/** Handles both "forgot password" links and new-account invitation links (same token mechanism). */
export function ResetPasswordPage() {
  const { t } = useTranslation();
  const errorMessage = useErrorMessage();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const schema = withConfirm({}, t('auth.passwordsDontMatch'));
  const { control, handleSubmit, formState, setError: setFieldError } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { new_password: '', confirm: '' },
  });
  const onSubmit = async (v: { new_password: string }) => {
    setError(null);
    try {
      await api.post('/auth/password/reset', { token, new_password: v.new_password });
      setDone(true);
    } catch (e) {
      if (!applyServerErrors(e, setFieldError, ['new_password'])) setError(errorMessage(e));
    }
  };
  return (
    <AuthCard title={t('auth.resetTitle')} icon={<KeyIcon />}>
      <Stack spacing={2}>
        {!token && <Alert severity="error">{t('auth.missingToken')}</Alert>}
        {done ? (
          <Alert severity="success">{t('auth.resetDone')}</Alert>
        ) : (
          token && (
            <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}>
              <Stack spacing={2}>
                {error && <Alert severity="error">{error}</Alert>}
                <FormTextField
                  control={control}
                  name="new_password"
                  type="password"
                  label={t('auth.newPassword')}
                  helperText={t('auth.passwordHint')}
                  autoComplete="new-password"
                  autoFocus
                />
                <FormTextField
                  control={control}
                  name="confirm"
                  type="password"
                  label={t('auth.confirmPassword')}
                  autoComplete="new-password"
                />
                <Button type="submit" variant="contained" size="large" disabled={formState.isSubmitting}>
                  {t('common.save')}
                </Button>
              </Stack>
            </Box>
          )
        )}
        <Link component={RouterLink} to="/login" textAlign="center" variant="body2">
          {t('auth.backToLogin')}
        </Link>
      </Stack>
    </AuthCard>
  );
}
