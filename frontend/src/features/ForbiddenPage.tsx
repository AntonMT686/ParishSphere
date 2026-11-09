import BlockIcon from '@mui/icons-material/BlockOutlined';
import Button from '@mui/material/Button';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { EmptyState } from '@/design-system';

export function ForbiddenPage() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={<BlockIcon />}
      title={t('errors.forbiddenTitle')}
      description={t('errors.forbiddenBody')}
      action={
        <Button component={RouterLink} to="/" variant="contained">
          {t('common.backToDashboard')}
        </Button>
      }
    />
  );
}
