import KeyIcon from '@mui/icons-material/KeyOutlined';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/auth/authStore';
import { AuthCard } from './AuthCard';
import { ChangePasswordForm } from './ChangePasswordForm';

/** Forced password change (account created by an administrator with a temporary password). */
export function ChangePasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const logout = useAuthStore((s) => s.logout);
  return (
    <AuthCard title={t('auth.changeTitle')} subtitle={t('auth.changeRequired')} icon={<KeyIcon />}>
      <Stack spacing={2}>
        <ChangePasswordForm onDone={() => navigate('/', { replace: true })} />
        <Button onClick={() => void logout('logout')}>{t('common.signOut')}</Button>
      </Stack>
    </AuthCard>
  );
}
