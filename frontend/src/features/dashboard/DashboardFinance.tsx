import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { useCan } from '@/auth/authStore';
import { inr, useFinSummary } from '@/features/finance/api';

function Figure({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h3" color={color} sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
    </div>
  );
}

/** Money in / out this month and this financial year (within the user's finance scope). */
export function DashboardFinance() {
  const { t } = useTranslation();
  const can = useCan();
  const { data } = useFinSummary();
  if (!data) return null;
  const link = can(['finance.view', 'finance.create']) ? '/finance/transactions' : can('finance_period.view') ? '/finance/statements' : null;
  return (
    <Grid size={12}>
      <Card>
        <CardHeader title={t('dashboard.finance')} subheader={data.last_released ? t('dashboard.lastReleased', { month: data.last_released }) : undefined}
          action={link && <Button size="small" component={RouterLink} to={link}>{t('dashboard.viewAll')}</Button>} />
        <CardContent sx={{ pt: 0 }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 2, sm: 5 }} flexWrap="wrap" useFlexGap>
            <Figure label={t('finance.incomeMonth', { month: data.month })} value={inr(data.income)} color="success.main" />
            <Figure label={t('finance.expenseMonth', { month: data.month })} value={inr(data.expense)} color="error.main" />
            <Figure label={t('finance.fyNet', { fy: data.fy_label })} value={inr(Number(data.fy_income) - Number(data.fy_expense))} />
            {data.balance != null && <Figure label={t('finance.balanceNow')} value={inr(data.balance)} />}
            <Figure label={t('finance.awaitingApproval')} value={String(data.pending_entries)} color={data.pending_entries ? 'warning.main' : undefined} />
          </Stack>
        </CardContent>
      </Card>
    </Grid>
  );
}
