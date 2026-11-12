import DownloadIcon from '@mui/icons-material/DownloadOutlined';
import LockIcon from '@mui/icons-material/LockOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { FinPeriod } from '@/api/types';
import { PageHeader, StatCard, StatusBadge, useFeedback } from '@/design-system';
import { ApprovalSection } from '@/features/activities/shared';
import { wfKeys } from '@/features/workflow/api';
import { formatDateTime } from '@/lib/format';
import { downloadBlob, finKeys, inr, usePeriod } from './api';

interface Snap {
  label: string; version?: number; totals: Record<'opening' | 'income' | 'expense' | 'surplus' | 'closing', string>;
  accounts: { code: string; name: string; kind: string; org_unit: string | null; opening: string; income: string; expense: string; transfers_in: string; transfers_out: string; closing: string }[];
  income_by_category: { code: string; name: string; amount: string }[];
  expense_by_category: { code: string; name: string; amount: string }[];
  organisations: { name: string; type: string; income: string; expense: string; net: string }[];
  pending: { code: string; date: string; description: string; amount: string; status: string }[];
  transactions: number;
}

function Breakdown({ title, rows }: { title: string; rows: { name: string; amount: string }[] }) {
  const { t } = useTranslation();
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={title} />
      <CardContent sx={{ pt: 0 }}>
        {rows.length === 0 ? <Typography variant="body2" color="text.secondary">—</Typography> : (
          <Table size="small" aria-label={title}><TableBody>
            {rows.map((r) => <TableRow key={r.name}><TableCell>{r.name}</TableCell><TableCell align="right">{inr(r.amount)}</TableCell></TableRow>)}
            <TableRow><TableCell><strong>{t('finance.total')}</strong></TableCell><TableCell align="right"><strong>{inr(rows.reduce((s, r) => s + Number(r.amount), 0))}</strong></TableCell></TableRow>
          </TableBody></Table>
        )}
      </CardContent>
    </Card>
  );
}

export function StatementPage() {
  const { periodKey = '' } = useParams();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const { data: p } = usePeriod(periodKey);
  const [closing, setClosing] = useState(false);
  const [reopening, setReopening] = useState(false);
  const [text, setText] = useState('');
  const done = (np: FinPeriod, msg: string) => {
    qc.setQueryData([...finKeys.periods, periodKey], np);
    void qc.invalidateQueries({ queryKey: finKeys.all });
    void qc.invalidateQueries({ queryKey: wfKeys.all });
    toast(msg);
    setClosing(false); setReopening(false); setText('');
  };
  const act = useMutation({
    mutationFn: async ({ what, body }: { what: 'close' | 'release' | 'reopen'; body?: object }) => (await api.post<FinPeriod>(`/finance/periods/${periodKey}/${what}`, body ?? {})).data,
    onSuccess: (np, v) => done(np, t(`finance.done.${v.what}`)),
    onError: toastError,
  });
  if (!p) return <Skeleton variant="rounded" height={480} />;
  const s = p.snapshot as unknown as Snap;
  const current = p.statements.find((x) => x.is_current);
  return (
    <>
      <PageHeader
        title={t('finance.statementFor', { month: p.label })}
        subtitle={p.live ? t('finance.liveFigures') : t('finance.versionN', { n: current?.version })}
        breadcrumbs={[{ label: t('nav.finance') }, { label: t('nav.statements'), to: '/finance/statements' }, { label: p.label }]}
        actions={
          <Stack direction="row" spacing={1}>
            {p.can_reopen && <Button color="inherit" onClick={() => setReopening(true)}>{t('finance.reopen')}</Button>}
            {p.can_close && <Button variant="contained" onClick={() => setClosing(true)}>{t('finance.closeMonth')}</Button>}
            {p.can_release && <Button variant="contained" startIcon={<LockIcon />} onClick={async () => {
              if (await confirm({ title: t('finance.releaseConfirm', { month: p.label }), message: t('finance.releaseHint') })) act.mutate({ what: 'release' });
            }}>{t('finance.release')}</Button>}
          </Stack>
        }
      />
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
        <StatusBadge status={p.status} />
        {p.status === 'RELEASED' && <Typography variant="body2" color="text.secondary">{t('finance.releasedBy', { name: p.released_by ?? '—', when: formatDateTime(p.released_at) })}</Typography>}
      </Stack>
      {p.revision_reason && p.status === 'OPEN' && <Alert severity="warning" sx={{ mb: 2 }}>{t('finance.reopenedBanner', { reason: p.revision_reason })}</Alert>}
      {p.status === 'UNDER_REVIEW' && <Alert severity="info" sx={{ mb: 2 }}>{t('finance.underReviewBanner')}</Alert>}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {(['opening', 'income', 'expense', 'closing'] as const).map((k) => (
          <Grid key={k} size={{ xs: 12, sm: 6, lg: 3 }}>
            <StatCard label={t(`finance.totals.${k}`)} value={inr(s.totals[k])} tone={k === 'income' ? 'success' : k === 'expense' ? 'error' : 'primary'} />
          </Grid>
        ))}
      </Grid>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card sx={{ mb: 2, overflowX: 'auto' }}>
            <CardHeader title={t('nav.accounts')} subheader={t('finance.entriesN', { count: s.transactions })} />
            <Table size="small" aria-label={t('nav.accounts')}>
              <TableHead><TableRow>
                <TableCell>{t('finance.account')}</TableCell><TableCell align="right">{t('finance.totals.opening')}</TableCell>
                <TableCell align="right">{t('finance.kind.INCOME')}</TableCell><TableCell align="right">{t('finance.kind.EXPENSE')}</TableCell>
                <TableCell align="right">{t('finance.transfers')}</TableCell><TableCell align="right">{t('finance.closing')}</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {s.accounts.map((a) => (
                  <TableRow key={a.code}>
                    <TableCell>{a.name}{a.org_unit && <Typography variant="caption" color="text.secondary" component="div">{a.org_unit}</Typography>}</TableCell>
                    <TableCell align="right">{inr(a.opening)}</TableCell><TableCell align="right">{inr(a.income)}</TableCell><TableCell align="right">{inr(a.expense)}</TableCell>
                    <TableCell align="right">{inr(Number(a.transfers_in) - Number(a.transfers_out))}</TableCell><TableCell align="right"><strong>{inr(a.closing)}</strong></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, md: 6 }}><Breakdown title={t('finance.incomeByCategory')} rows={s.income_by_category} /></Grid>
            <Grid size={{ xs: 12, md: 6 }}><Breakdown title={t('finance.expenseByCategory')} rows={s.expense_by_category} /></Grid>
          </Grid>
          <Card sx={{ mb: 2, overflowX: 'auto' }}>
            <CardHeader title={t('finance.byOrganisation')} />
            <Table size="small" aria-label={t('finance.byOrganisation')}>
              <TableHead><TableRow><TableCell>{t('activities.organisation')}</TableCell><TableCell align="right">{t('finance.kind.INCOME')}</TableCell><TableCell align="right">{t('finance.kind.EXPENSE')}</TableCell><TableCell align="right">{t('finance.net')}</TableCell></TableRow></TableHead>
              <TableBody>
                {s.organisations.length === 0 && <TableRow><TableCell colSpan={4}>—</TableCell></TableRow>}
                {s.organisations.map((o) => <TableRow key={o.name}><TableCell>{o.name}</TableCell><TableCell align="right">{inr(o.income)}</TableCell><TableCell align="right">{inr(o.expense)}</TableCell><TableCell align="right">{inr(o.net)}</TableCell></TableRow>)}
              </TableBody>
            </Table>
          </Card>
          {s.pending.length > 0 && (
            <Card>
              <CardHeader title={t('finance.pendingEntries')} subheader={t('finance.pendingHint')} />
              <CardContent sx={{ pt: 0 }}>
                <Stack spacing={0.75}>
                  {s.pending.map((x) => (
                    <Stack key={x.code} direction="row" spacing={1} alignItems="center">
                      <Link component={RouterLink} to={`/finance/transactions?period=${periodKey}`} variant="body2">{x.code}</Link>
                      <Typography variant="body2" sx={{ flexGrow: 1 }} noWrap>{x.description}</Typography>
                      <Typography variant="body2">{inr(x.amount)}</Typography><StatusBadge status={x.status} />
                    </Stack>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          )}
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack spacing={2}>
            <Card>
              <CardHeader title={t('finance.statementFiles')} />
              <CardContent sx={{ pt: 0 }}>
                {p.statements.length === 0 && <Typography variant="body2" color="text.secondary">{t('finance.noStatementYet')}</Typography>}
                <Stack spacing={1.5}>
                  {p.statements.map((v) => (
                    <div key={v.id}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="body2" fontWeight={600}>{t('finance.versionN', { n: v.version })}</Typography>
                        {v.is_current && <Chip size="small" color="primary" variant="outlined" label={t('workflow.latest')} />}
                        {v.released_at && <Chip size="small" color="success" label={t('status.RELEASED', { defaultValue: 'Released' })} />}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" component="div">{formatDateTime(v.generated_at)}{v.generated_by ? ` · ${v.generated_by}` : ''}</Typography>
                      {v.revision_reason && <Typography variant="caption" component="div">{t('finance.revision')}: {v.revision_reason}</Typography>}
                      <Tooltip title={v.sha256}><Typography variant="caption" color="text.secondary" component="div" sx={{ fontFamily: 'monospace' }}>SHA-256 {v.sha256.slice(0, 16)}…</Typography></Tooltip>
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        {(['pdf', 'xlsx'] as const).map((fmt) => (
                          <Button key={fmt} size="small" startIcon={<DownloadIcon />} onClick={async () => {
                            try {
                              const d = (await api.get<{ url: string; filename: string }>(`/finance/statements/${v.id}/download`, { params: { format: fmt } })).data;
                              if (d.url.startsWith('/api/v1/')) await downloadBlob(d.url.replace('/api/v1', ''), d.filename);
                              else window.open(d.url, '_blank', 'noopener');
                            } catch (e) { toastError(e); }
                          }}>{fmt.toUpperCase()}</Button>
                        ))}
                      </Stack>
                    </div>
                  ))}
                </Stack>
              </CardContent>
            </Card>
            <ApprovalSection entityType="FIN_PERIOD" entityId={p.id} onChange={() => void qc.invalidateQueries({ queryKey: finKeys.periods })} />
          </Stack>
        </Grid>
      </Grid>
      <Dialog open={closing} onClose={() => setClosing(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('finance.closeTitle', { month: p.label })}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>{t('finance.closeHint')}</Typography>
          <TextField label={t('workflow.comment')} value={text} onChange={(e) => setText(e.target.value)} multiline minRows={2} fullWidth />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClosing(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={act.isPending} onClick={() => act.mutate({ what: 'close', body: { comment: text.trim() || null } })}>{t('finance.closeAndSubmit')}</Button>
        </DialogActions>
      </Dialog>
      <Dialog open={reopening} onClose={() => setReopening(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('finance.reopenTitle', { month: p.label })}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>{t('finance.reopenHint')}</Alert>
          <TextField label={t('finance.reopenReason')} value={text} onChange={(e) => setText(e.target.value)} multiline minRows={2} fullWidth required />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReopening(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" color="warning" disabled={text.trim().length < 5 || act.isPending} onClick={() => act.mutate({ what: 'reopen', body: { reason: text.trim() } })}>{t('finance.reopen')}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
