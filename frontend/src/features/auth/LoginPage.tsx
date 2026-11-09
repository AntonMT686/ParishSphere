import { zodResolver } from '@hookform/resolvers/zod';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { useTenantBranding } from '@/api/tenant';
import { useAuthStore } from '@/auth/authStore';
import { FormTextField, useErrorMessage } from '@/design-system';
import { getStoredParishCode, setStoredParishCode, subdomainFromHost } from '@/lib/tenant';
import { AuthCard } from './AuthCard';

const schema = z.object({
  parishCode: z.string().trim().max(20).optional(),
  username: z.string().trim().min(1, 'Required'),
  password: z.string().min(1, 'Required'),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const login = useAuthStore((s) => s.login);
  const errorMessage = useErrorMessage();
  const [params] = useSearchParams();
  const needsParishCode = subdomainFromHost(window.location.hostname) === null;
  const { data: branding, isError: unknownParish } = useTenantBranding();
  const reason = params.get('reason');
  const [error, setError] = useState<string | null>(null);
  const { control, handleSubmit, formState } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { parishCode: getStoredParishCode() ?? '', username: '', password: '' },
  });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    if (needsParishCode && values.parishCode) {
      setStoredParishCode(values.parishCode);
      await queryClient.invalidateQueries({ queryKey: ['tenant'] });
    }
    try {
      await login(values.username, values.password);
      // RedirectIfAuthenticated sends the user to `from` (or the dashboard).
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <AuthCard
      title={t('auth.welcome')}
      subtitle={branding ? t('auth.signInTo', { parish: branding.display_name }) : t('app.tagline')}
    >
      <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}>
        <Stack spacing={2}>
          {reason === 'timeout' && !error && <Alert severity="info">{t('auth.sessionExpired')}</Alert>}
          {reason === 'revoked' && !error && <Alert severity="warning">{t('auth.revoked')}</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
          {unknownParish && !needsParishCode && <Alert severity="warning">{t('auth.unknownParish')}</Alert>}
          {needsParishCode && (
            <FormTextField
              control={control}
              name="parishCode"
              label={t('auth.parishCode')}
              autoComplete="organization"
              slotProps={{ htmlInput: { style: { textTransform: 'uppercase' } } }}
            />
          )}
          <FormTextField control={control} name="username" label={t('auth.username')} autoComplete="username" autoFocus />
          <FormTextField
            control={control}
            name="password"
            label={t('auth.password')}
            type="password"
            autoComplete="current-password"
          />
          <Button type="submit" variant="contained" size="large" disabled={formState.isSubmitting}>
            {t('auth.signIn')}
          </Button>
          <Link component={RouterLink} to="/forgot-password" textAlign="center" variant="body2">
            {t('auth.forgot')}
          </Link>
        </Stack>
      </Box>
    </AuthCard>
  );
}
