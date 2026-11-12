import Card from '@mui/material/Card';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { PageHeader, StatusBadge } from '@/design-system';
import { inr, usePeriods } from './api';

export function StatementsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data = [] } = usePeriods();
  return (
    <>
      <PageHeader title={t('nav.statements')} subtitle={t('finance.statementsSubtitle')} breadcrumbs={[{ label: t('nav.finance') }, { label: t('nav.statements') }]} />
      <Card sx={{ overflowX: 'auto' }}>
        <Table aria-label={t('nav.statements')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('finance.month')}</TableCell><TableCell>{t('common.status')}</TableCell>
              <TableCell align="right">{t('finance.kind.INCOME')}</TableCell><TableCell align="right">{t('finance.kind.EXPENSE')}</TableCell>
              <TableCell align="right">{t('finance.closing')}</TableCell><TableCell align="right">{t('finance.undecided')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.map((p) => (
              <TableRow key={p.key} hover sx={{ cursor: 'pointer' }} onClick={() => navigate(`/finance/statements/${p.key}`)}>
                <TableCell><Typography variant="body2" fontWeight={600}>{p.label}</Typography>
                  {p.versions > 1 && <Typography variant="caption" color="text.secondary">{t('finance.versionsN', { count: p.versions })}</Typography>}</TableCell>
                <TableCell><StatusBadge status={p.status} /></TableCell>
                <TableCell align="right">{inr(p.income)}</TableCell><TableCell align="right">{inr(p.expense)}</TableCell>
                <TableCell align="right">{inr(p.closing)}</TableCell>
                <TableCell align="right">{p.pending || '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1.5 }}>{t('finance.statementsHint')}</Typography>
    </>
  );
}
