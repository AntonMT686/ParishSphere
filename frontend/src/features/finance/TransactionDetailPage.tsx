import EditIcon from '@mui/icons-material/EditOutlined';
import ReceiptIcon from '@mui/icons-material/ReceiptLongOutlined';
import SendIcon from '@mui/icons-material/SendOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { FinTxn } from '@/api/types';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { ApprovalSection, AttachmentsCard, Fact } from '@/features/activities/shared';
import { wfKeys } from '@/features/workflow/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { downloadBlob, finKeys, useTxn } from './api';
import { TransactionDialog } from './TransactionDialog';
import { Amount } from './TransactionsPage';

export function TransactionDetailPage() {
  const { txnId = '' } = useParams();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const { data: x, isError } = useTxn(txnId);
  const [editing, setEditing] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: finKeys.all });
  const submit = useMutation({
    mutationFn: async () => (await api.post<FinTxn>(`/finance/transactions/${txnId}/submit`, {})).data,
    onSuccess: (n) => { qc.setQueryData([...finKeys.txns, n.id], n); refresh(); void qc.invalidateQueries({ queryKey: wfKeys.all }); toast(t('activities.submitted')); },
    onError: toastError,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/finance/transactions/${txnId}`),
    onSuccess: () => { refresh(); toast(t('finance.deleted')); navigate('/finance/transactions', { replace: true }); },
    onError: toastError,
  });
  if (isError) return <EmptyState title={t('finance.notFound')} />;
  if (!x) return <Skeleton variant="rounded" height={420} />;
  const receipt = x.kind === 'INCOME' && x.status === 'APPROVED' && Number(x.amount) > 0;
  return (
    <>
      <PageHeader
        title={x.description}
        subtitle={`${x.code} · ${x.org_unit?.name ?? t('activities.parishLevel')} · ${x.period}`}
        breadcrumbs={[{ label: t('nav.finance') }, { label: t('nav.transactions'), to: '/finance/transactions' }, { label: x.code }]}
        actions={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {x.can_delete && <Button color="error" onClick={async () => { if (await confirm({ title: t('finance.deleteConfirm'), destructive: true })) remove.mutate(); }}>{t('common.delete')}</Button>}
            {receipt && <Button startIcon={<ReceiptIcon />} onClick={() => void downloadBlob(`/finance/transactions/${x.id}/receipt.pdf`, `receipt-${x.code}.pdf`)}>{t('finance.receipt')}</Button>}
            {x.can_correct && <Button onClick={() => setCorrecting(true)}>{t('finance.correct')}</Button>}
            {x.can_edit && <Button startIcon={<EditIcon />} onClick={() => setEditing(true)}>{t('common.edit')}</Button>}
            {x.can_submit && <Button variant="contained" startIcon={<SendIcon />} disabled={submit.isPending} onClick={() => submit.mutate()}>
              {x.status === 'REWORK' ? t('activities.resubmit') : t('activities.submit')}</Button>}
          </Stack>
        }
      />
      {x.period_status !== 'OPEN' && x.status !== 'APPROVED' && <Alert severity="warning" sx={{ mb: 2 }}>{t('finance.periodClosedBanner', { period: x.period })}</Alert>}
      {x.status === 'REWORK' && <Alert severity="warning" sx={{ mb: 2 }}>{t('activities.reworkBanner')}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={<Amount kind={x.kind} amount={x.amount} />} subheader={t(`finance.kind.${x.kind}`)} action={<StatusBadge status={x.status} />} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('finance.date')}>{formatDate(x.txn_date)}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('finance.category')}>{x.category?.name ?? '—'}</Fact></Grid>
                <Grid size={{ xs: 12, md: 4 }}><Fact label={t('finance.account')}>{x.to_account ? `${x.account.name} → ${x.to_account.name}` : x.account.name}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('finance.method')}>{t(`finance.methods.${x.payment_method}`)}</Fact></Grid>
                <Grid size={{ xs: 6, md: 4 }}><Fact label={t('finance.reference')}>{x.reference_no}</Fact></Grid>
                <Grid size={{ xs: 12, md: 4 }}><Fact label={x.kind === 'INCOME' ? t('finance.receivedFrom') : t('finance.paidTo')}>{x.payer_payee}{x.family ? ` (${x.family.name})` : ''}</Fact></Grid>
                <Grid size={12}><Fact label={t('finance.particulars')}>{x.description}</Fact></Grid>
              </Grid>
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('finance.trail')} />
            <CardContent sx={{ pt: 0 }}>
              <Grid container spacing={2}>
                <Grid size={{ xs: 12, sm: 4 }}><Fact label={t('finance.enteredBy')}>{x.entered_by}<Typography variant="caption" color="text.secondary" component="div">{formatDateTime(x.created_at)}</Typography></Fact></Grid>
                <Grid size={{ xs: 12, sm: 4 }}><Fact label={t('finance.reviewedBy')}>{x.reviewed_by}</Fact></Grid>
                <Grid size={{ xs: 12, sm: 4 }}><Fact label={t('finance.approvedBy')}>{x.approved_by}{x.approved_at && <Typography variant="caption" color="text.secondary" component="div">{formatDateTime(x.approved_at)}</Typography>}</Fact></Grid>
                {x.adjusts && <Grid size={12}><Fact label={t('finance.corrects')}><Link component={RouterLink} to={`/finance/transactions/${x.adjusts.id}`}>{x.adjusts.name}</Link></Fact></Grid>}
                {x.corrections.length > 0 && (
                  <Grid size={12}><Fact label={t('finance.correctedBy')}>
                    <Stack direction="row" spacing={1}>{x.corrections.map((c) => <Link key={c.id} component={RouterLink} to={`/finance/transactions/${c.id}`}>{c.name}</Link>)}</Stack>
                  </Fact></Grid>
                )}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Stack spacing={2}>
            <ApprovalSection entityType="FIN_TRANSACTION" entityId={x.id} onChange={refresh} />
            <AttachmentsCard base={`/finance/transactions/${x.id}`} canAdd={x.can_attach} canRemove={x.can_edit} />
          </Stack>
        </Grid>
      </Grid>
      <TransactionDialog open={editing} onClose={() => setEditing(false)} txn={x} />
      <TransactionDialog open={correcting} onClose={() => setCorrecting(false)} corrects={x} />
    </>
  );
}
