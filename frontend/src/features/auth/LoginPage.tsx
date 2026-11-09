import { zodResolver } from '@hookform/resolvers/zod';
import LockIcon from '@mui/icons-material/LockOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { ApiError, api, setAccessToken } from '@/api/client';
import { useTenantBranding } from '@/api/tenant';
import { getStoredParishCode, setStoredParishCode, subdomainFromHost } from '@/lib/tenant';

const schema = z.object({
  parishCode: z.string().trim().max(20).optional(),
  username: z.string().trim().min(1),
  password: z.string().min(1),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const needsParishCode = subdomainFromHost(window.location.hostname) === null;
  const { data: branding, isError: unknownParish } = useTenantBranding();
  const [error, setError] = useState<string | null>(
    params.get('reason') === 'timeout' ? t('auth.sessionExpired') : null,
  );
  const {
    register,
    handleSubmit,
    formState: { isSubmitting, errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { parishCode: getStoredParishCode() ?? '' },
  });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    if (needsParishCode && values.parishCode) {
      setStoredParishCode(values.parishCode);
      await queryClient.invalidateQueries({ queryKey: ['tenant'] });
    }
    try {
      const { data } = await api.post<{ access_token: string }>('/auth/login', {
        username: values.username,
        password: values.password,
      });
      setAccessToken(data.access_token);
      navigate('/', { replace: true });
    } catch (e) {
      const code = e instanceof ApiError ? e.code : 'INTERNAL_ERROR';
      setError(t(`errors.${code}`, { defaultValue: e instanceof Error ? e.message : t('errors.INTERNAL_ERROR') }));
    }
  };

  return (
    <Card>
      <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
        <Stack spacing={1} alignItems="center" sx={{ mb: 3 }}>
          <Box sx={{ bgcolor: 'primary.main', color: 'primary.contrastText', borderRadius: '50%', p: 1.25, display: 'flex' }}>
            <LockIcon />
          </Box>
          <Typography variant="h2" component="h1">
            {t('auth.welcome')}
          </Typography>
          <Typography color="text.secondary" textAlign="center">
            {branding ? t('auth.signInTo', { parish: branding.display_name }) : t('app.tagline')}
          </Typography>
        </Stack>
        <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            {unknownParish && !needsParishCode && <Alert severity="warning">{t('auth.unknownParish')}</Alert>}
            {needsParishCode && (
              <TextField
                label={t('auth.parishCode')}
                autoComplete="organization"
                inputProps={{ style: { textTransform: 'uppercase' } }}
                {...register('parishCode')}
              />
            )}
            <TextField
              label={t('auth.username')}
              autoComplete="username"
              autoFocus
              error={Boolean(errors.username)}
              {...register('username')}
            />
            <TextField
              label={t('auth.password')}
              type="password"
              autoComplete="current-password"
              error={Boolean(errors.password)}
              {...register('password')}
            />
            <Button type="submit" variant="contained" size="large" disabled={isSubmitting}>
              {t('auth.signIn')}
            </Button>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}
