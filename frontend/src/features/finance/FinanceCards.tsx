import AccountBalanceIcon from '@mui/icons-material/AccountBalanceWalletOutlined';
import ArrowDownIcon from '@mui/icons-material/SouthWest';
import ArrowUpIcon from '@mui/icons-material/NorthEast';
import PendingIcon from '@mui/icons-material/HourglassEmptyOutlined';
import Grid from '@mui/material/Grid2';
import { useTranslation } from 'react-i18next';
import { StatCard } from '@/design-system';
import { inr, useFinSummary } from './api';

/** This month / financial year at a glance, within the user's scope. */
export function FinanceCards() {
  const { t } = useTranslation();
  const { data, isLoading } = useFinSummary();
  if (!isLoading && !data) return null;
  return (
    <Grid container spacing={2} sx={{ mb: 2 }}>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <StatCard label={t('finance.incomeMonth', { month: data?.month ?? '' })} value={inr(data?.income)} icon={<ArrowDownIcon />} tone="success" loading={isLoading} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <StatCard label={t('finance.expenseMonth', { month: data?.month ?? '' })} value={inr(data?.expense)} icon={<ArrowUpIcon />} tone="error" loading={isLoading} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <StatCard label={data?.balance != null ? t('finance.balanceNow') : t('finance.fySurplus', { fy: data?.fy_label ?? '' })}
          value={data?.balance != null ? inr(data.balance) : inr(Number(data?.fy_income ?? 0) - Number(data?.fy_expense ?? 0))}
          icon={<AccountBalanceIcon />} tone="primary" loading={isLoading} />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <StatCard label={t('finance.awaitingApproval')} value={String(data?.pending_entries ?? 0)} icon={<PendingIcon />} tone="warning" loading={isLoading} />
      </Grid>
    </Grid>
  );
}
