import { zodResolver } from '@hookform/resolvers/zod';
import MailIcon from '@mui/icons-material/MarkEmailReadOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { z } from 'zod';
import { api } from '@/api/client';
import { FormTextField, useErrorMessage } from '@/design-system';
import { AuthCard } from './AuthCard';

const schema = z.object({ username: z.string().trim().min(1, 'Required') });

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const errorMessage = useErrorMessage();
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { control, handleSubmit, formState } = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { username: '' },
  });
  const onSubmit = async (v: z.infer<typeof schema>) => {
    setError(null);
    try {
      await api.post('/auth/password/forgot', v);
      setSent(true);
    } catch (e) {
      setError(errorMessage(e));
    }
  };
  return (
    <AuthCard title={t('auth.forgotTitle')} subtitle={sent ? undefined : t('auth.forgotBody')} icon={<MailIcon />}>
      <Stack spacing={2}>
        {sent ? (
          <Alert severity="success">{t('auth.linkSent')}</Alert>
        ) : (
          <Box component="form" noValidate onSubmit={handleSubmit(onSubmit)}>
            <Stack spacing={2}>
              {error && <Alert severity="error">{error}</Alert>}
              <FormTextField control={control} name="username" label={t('auth.username')} autoFocus />
              <Button type="submit" variant="contained" size="large" disabled={formState.isSubmitting}>
                {t('auth.sendLink')}
              </Button>
            </Stack>
          </Box>
        )}
        <Link component={RouterLink} to="/login" textAlign="center" variant="body2">
          {t('auth.backToLogin')}
        </Link>
      </Stack>
    </AuthCard>
  );
}
