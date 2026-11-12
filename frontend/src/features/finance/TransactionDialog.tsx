import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Grid from '@mui/material/Grid2';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import type { FamilyListItem, FinTxn } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { useFeedback } from '@/design-system';
import { OrgUnitSelect, PARISH } from '@/features/activities/shared';
import { FamilyPicker } from '@/features/people/pickers';
import { finKeys, METHODS, useAccounts, useCategories } from './api';

type Kind = 'INCOME' | 'EXPENSE' | 'TRANSFER';
interface Form {
  kind: Kind; txn_date: string; org_unit_id: string; category_id: string; account_id: string; to_account_id: string;
  amount: string; payment_method: string; reference_no: string; description: string; payer_payee: string;
}
const today = () => new Date().toISOString().slice(0, 10);

/** New entry, edit of a draft (``txn``), or a correction of an approved entry (``corrects``). */
export function TransactionDialog({ open, onClose, txn, corrects }: { open: boolean; onClose: () => void; txn?: FinTxn; corrects?: FinTxn }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const can = useCan();
  const { toast, toastError } = useFeedback();
  const { data: accounts = [] } = useAccounts();
  const { data: categories = [] } = useCategories();
  const [form, setForm] = useState<Form | null>(null);
  const [family, setFamily] = useState<FamilyListItem | null>(null);
  useEffect(() => {
    if (!open) return;
    const src = txn ?? corrects;
    setFamily(null);
    setForm({
      kind: (src?.kind as Kind) ?? 'INCOME', txn_date: txn?.txn_date ?? today(), org_unit_id: src?.org_unit?.id ?? PARISH,
      category_id: src?.category?.id ?? '', account_id: src?.account.id ?? '', to_account_id: src?.to_account?.id ?? '',
      amount: txn ? String(txn.amount) : corrects ? '' : '', payment_method: src?.payment_method ?? 'CASH',
      reference_no: txn?.reference_no ?? '', payer_payee: src?.payer_payee ?? '',
      description: txn?.description ?? (corrects ? t('finance.correctionOf', { code: corrects.code }) : ''),
    });
  }, [open, txn, corrects, t]);
  const save = useMutation({
    mutationFn: async (f: Form) => {
      const body = {
        kind: f.kind, txn_date: f.txn_date, org_unit_id: f.org_unit_id || null, category_id: f.kind === 'TRANSFER' ? null : f.category_id || null,
        account_id: f.account_id, to_account_id: f.kind === 'TRANSFER' ? f.to_account_id || null : null, amount: f.amount,
        payment_method: f.payment_method, reference_no: f.reference_no.trim() || null, description: f.description.trim(),
        payer_payee: f.payer_payee.trim() || null, family_id: family?.id ?? txn?.family?.id ?? null,
        adjusts_transaction_id: corrects?.id ?? (txn?.adjusts?.id ?? null),
      };
      return txn ? (await api.put<FinTxn>(`/finance/transactions/${txn.id}`, body)).data : (await api.post<FinTxn>('/finance/transactions', body)).data;
    },
    onSuccess: (x) => {
      qc.setQueryData([...finKeys.txns, x.id], x);
      void qc.invalidateQueries({ queryKey: finKeys.all });
      toast(t('common.saved'));
      onClose();
      if (!txn) navigate(`/finance/transactions/${x.id}`);
    },
    onError: toastError,
  });
  if (!form) return null;
  const set = (p: Partial<Form>) => setForm({ ...form, ...p });
  const usable = accounts.filter((a) => a.org_unit === null || a.org_unit.id === form.org_unit_id);
  const cats = categories.filter((c) => c.kind === form.kind);
  const correcting = Boolean(corrects || txn?.adjusts);
  const amountOk = form.amount !== '' && Number(form.amount) !== 0 && (correcting || Number(form.amount) > 0);
  const valid = amountOk && form.account_id && form.description.trim().length >= 2 && form.txn_date
    && (form.kind === 'TRANSFER' ? form.to_account_id && form.to_account_id !== form.account_id : form.category_id);
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{txn ? t('finance.editEntry') : corrects ? t('finance.correctEntry') : t('finance.newEntry')}</DialogTitle>
      <DialogContent>
        {correcting && <Alert severity="info" sx={{ mb: 2 }}>{t('finance.correctionHint', { code: corrects?.code ?? txn?.adjusts?.name })}</Alert>}
        <Grid container spacing={2} sx={{ pt: 1 }}>
          <Grid size={12}>
            <ToggleButtonGroup exclusive value={form.kind} disabled={correcting} aria-label={t('finance.kindLabel')}
              onChange={(_e, v: Kind | null) => v && set({ kind: v, category_id: '', to_account_id: '' })}>
              <ToggleButton value="INCOME" color="success">{t('finance.kind.INCOME')}</ToggleButton>
              <ToggleButton value="EXPENSE" color="error">{t('finance.kind.EXPENSE')}</ToggleButton>
              <ToggleButton value="TRANSFER" color="primary">{t('finance.kind.TRANSFER')}</ToggleButton>
            </ToggleButtonGroup>
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField type="date" label={t('finance.date')} value={form.txn_date} onChange={(e) => set({ txn_date: e.target.value })}
              slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: today() } }} required />
          </Grid>
          <Grid size={{ xs: 12, sm: 8 }}>
            <OrgUnitSelect permission="finance.create" autoSelect={!txn && !corrects} value={form.org_unit_id} disabled={correcting || txn?.status === 'REWORK'}
              onChange={(v) => setForm((cur) => (cur ? { ...cur, org_unit_id: v, account_id: '', to_account_id: '' } : cur))}
              current={txn?.org_unit ?? corrects?.org_unit ?? null} />
          </Grid>
          {form.kind !== 'TRANSFER' && (
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label={t('finance.category')} value={form.category_id} onChange={(e) => set({ category_id: e.target.value })} required disabled={correcting}>
                {cats.map((c) => <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>)}
              </TextField>
            </Grid>
          )}
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField select label={form.kind === 'TRANSFER' ? t('finance.fromAccount') : t('finance.account')} value={form.account_id}
              onChange={(e) => set({ account_id: e.target.value })} required helperText={usable.length === 0 ? t('finance.noAccount') : undefined}>
              {usable.map((a) => <MenuItem key={a.id} value={a.id}>{a.name}{a.org_unit ? ` · ${a.org_unit.name}` : ''}</MenuItem>)}
            </TextField>
          </Grid>
          {form.kind === 'TRANSFER' && (
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField select label={t('finance.toAccount')} value={form.to_account_id} onChange={(e) => set({ to_account_id: e.target.value })} required>
                {accounts.filter((a) => a.id !== form.account_id).map((a) => <MenuItem key={a.id} value={a.id}>{a.name}{a.org_unit ? ` · ${a.org_unit.name}` : ''}</MenuItem>)}
              </TextField>
            </Grid>
          )}
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField type="number" label={t('finance.amount')} value={form.amount} onChange={(e) => set({ amount: e.target.value })} required
              slotProps={{ input: { startAdornment: <InputAdornment position="start">₹</InputAdornment> }, htmlInput: { step: '0.01' } }}
              helperText={correcting ? t('finance.negativeHint') : undefined} />
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField select label={t('finance.method')} value={form.payment_method} onChange={(e) => set({ payment_method: e.target.value })}>
              {METHODS.map((m) => <MenuItem key={m} value={m}>{t(`finance.methods.${m}`)}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField label={t('finance.reference')} value={form.reference_no} onChange={(e) => set({ reference_no: e.target.value })} placeholder={t('finance.referenceHint')} />
          </Grid>
          {form.kind !== 'TRANSFER' && (
            <Grid size={{ xs: 12, sm: 6 }}>
              <TextField label={form.kind === 'INCOME' ? t('finance.receivedFrom') : t('finance.paidTo')} value={form.payer_payee} onChange={(e) => set({ payer_payee: e.target.value })} />
            </Grid>
          )}
          {form.kind === 'INCOME' && can('family.view') && (
            <Grid size={{ xs: 12, sm: 6 }}>
              <FamilyPicker label={txn?.family ? `${t('finance.family')}: ${txn.family.name}` : t('finance.family')} value={family}
                onChange={(f) => { setFamily(f); if (f && !form.payer_payee) set({ payer_payee: `${f.family_name} family` }); }} />
            </Grid>
          )}
          <Grid size={12}>
            <TextField label={t('finance.particulars')} value={form.description} onChange={(e) => set({ description: e.target.value })} required multiline minRows={2} />
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate(form)}>{t('finance.saveDraft')}</Button>
      </DialogActions>
    </Dialog>
  );
}
