import Chip, { type ChipProps } from '@mui/material/Chip';
import { useTranslation } from 'react-i18next';

type Tone = ChipProps['color'];

const STATUS_TONE: Record<string, Tone> = {
  ACTIVE: 'success',
  APPROVED: 'success',
  PUBLISHED: 'success',
  COMPLETED: 'success',
  RELEASED: 'success',
  DONE: 'success',
  DRAFT: 'default',
  OPEN: 'default',
  SUBMITTED: 'info',
  IN_REVIEW: 'info',
  IN_PROGRESS: 'info',
  UNDER_REVIEW: 'info',
  TRIAL: 'info',
  PENDING: 'warning',
  REWORK: 'warning',
  OVERDUE: 'warning',
  PROVISIONING: 'warning',
  REJECTED: 'error',
  SUSPENDED: 'error',
  FAILED: 'error',
  CANCELLED: 'default',
  INACTIVE: 'default',
  DECEASED: 'default',
  ARCHIVED: 'default',
};

export function statusTone(status: string): Tone {
  return STATUS_TONE[status.toUpperCase()] ?? 'default';
}

export interface StatusBadgeProps {
  status: string;
  size?: ChipProps['size'];
}

/** Consistent, translated status chip used across every module. */
export function StatusBadge({ status, size = 'small' }: StatusBadgeProps) {
  const { t } = useTranslation();
  const key = status.toUpperCase();
  return (
    <Chip
      size={size}
      color={statusTone(key)}
      variant={statusTone(key) === 'default' ? 'outlined' : 'filled'}
      label={t(`status.${key}`, { defaultValue: key.replace(/_/g, ' ') })}
    />
  );
}
