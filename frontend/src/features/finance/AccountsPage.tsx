import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tab from '@mui/material/Tab';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/api/client';
import type { FinAccount, FinCategory, OrgUnit } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { OrgUnitPicker } from '@/features/org/pickers';
import { formatDate } from '@/lib/format';
import { finKeys, inr, useAccounts, useCategories } from './api';

function AccountDialog({ open, onClose, account }: { open: boolean; onClose: () => void; account?: FinAccount }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [f, setF] = useState({ code: '', name: '', kind: 'CASH', bank_name: '', account_number_masked: '', opening_balance: '0', opening_date: new Date().toISOString().slice(0, 10), is_active: true });
  const [unit, setUnit] = useState<Pick<OrgUnit, 'id' | 'name' | 'code'> | null>(null);
  useEffect(() => {
    if (!open) return;
    setUnit(null);
    setF(account ? { code: account.code, name: account.name, kind: account.kind, bank_name: account.bank_name ?? '', account_number_masked: account.account_number_masked ?? '',
      opening_balance: String(account.opening_balance), opening_date: account.opening_date, is_active: account.is_active }
      : { code: '', name: '', kind: 'CASH', bank_name: '', account_number_masked: '', opening_balance: '0', opening_date: new Date().toISOString().slice(0, 10), is_active: true });
  }, [open, account]);
  const save = useMutation({
    mutationFn: async () => {
      if (account) await api.patch(`/finance/accounts/${account.id}`, { name: f.name, bank_name: f.bank_name || null, account_number_masked: f.account_number_masked || null, is_active: f.is_active });
      else await api.post('/finance/accounts', { code: f.code.toUpperCase(), name: f.name, kind: f.kind, org_unit_id: unit?.id ?? null, bank_name: f.bank_name || null,
        account_number_masked: f.account_number_masked || null, opening_balance: f.opening_balance || '0', opening_date: f.opening_date });
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: finKeys.all }); toast(t('common.saved')); onClose(); },
    onError: toastError,
  });
  const set = (p: Partial<typeof f>) => setF({ ...f, ...p });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{account ? t('finance.editAccount') : t('finance.newAccount')}</DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ pt: 1 }}>
          <Grid size={{ xs: 12, sm: 4 }}><TextField label={t('finance.code')} value={f.code} disabled={Boolean(account)} onChange={(e) => set({ code: e.target.value.toUpperCase() })} required helperText="CASH, SBI-MAIN…" /></Grid>
          <Grid size={{ xs: 12, sm: 8 }}><TextField label={t('common.name')} value={f.name} onChange={(e) => set({ name: e.target.value })} required /></Grid>
          <Grid size={{ xs: 12, sm: 4 }}>
            <TextField select label={t('finance.accountKind')} value={f.kind} disabled={Boolean(account)} onChange={(e) => set({ kind: e.target.value })}>
              {['CASH', 'BANK', 'DIGITAL'].map((k) => <MenuItem key={k} value={k}>{t(`finance.accountKinds.${k}`)}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 8 }}>
            {account ? <TextField label={t('activities.organisation')} value={account.org_unit?.name ?? t('activities.parishLevel')} disabled />
              : <OrgUnitPicker label={t('finance.heldBy')} value={unit} onChange={setUnit} />}
          </Grid>
          {f.kind !== 'CASH' && (
            <>
              <Grid size={{ xs: 12, sm: 7 }}><TextField label={t('finance.bank')} value={f.bank_name} onChange={(e) => set({ bank_name: e.target.value })} /></Grid>
              <Grid size={{ xs: 12, sm: 5 }}><TextField label={t('finance.accountNo')} value={f.account_number_masked} onChange={(e) => set({ account_number_masked: e.target.value })} helperText={t('finance.accountNoHint')} /></Grid>
            </>
          )}
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField type="number" label={t('finance.openingBalance')} value={f.opening_balance} disabled={Boolean(account)} onChange={(e) => set({ opening_balance: e.target.value })}
              slotProps={{ input: { startAdornment: <InputAdornment position="start">₹</InputAdornment> } }} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6 }}>
            <TextField type="date" label={t('finance.openingDate')} value={f.opening_date} disabled={Boolean(account)} onChange={(e) => set({ opening_date: e.target.value })} slotProps={{ inputLabel: { shrink: true } }} />
          </Grid>
          {account && <Grid size={12}><FormControlLabel control={<Switch checked={f.is_active} onChange={(e) => set({ is_active: e.target.checked })} />} label={t('finance.inUse')} /></Grid>}
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!f.name.trim() || (!account && f.code.length < 2) || save.isPending} onClick={() => save.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

function CategoryDialog({ open, onClose, category }: { open: boolean; onClose: () => void; category?: FinCategory }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [f, setF] = useState({ code: '', name: '', name_local: '', kind: 'INCOME', is_active: true });
  useEffect(() => {
    if (open) setF(category ? { code: category.code, name: category.name, name_local: category.name_local ?? '', kind: category.kind, is_active: category.is_active } : { code: '', name: '', name_local: '', kind: 'INCOME', is_active: true });
  }, [open, category]);
  const save = useMutation({
    mutationFn: async () => {
      if (category) await api.patch(`/finance/categories/${category.id}`, { name: f.name, name_local: f.name_local || null, is_active: f.is_active });
      else await api.post('/finance/categories', { code: f.code, name: f.name, name_local: f.name_local || null, kind: f.kind });
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: finKeys.categories }); toast(t('common.saved')); onClose(); },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>{category ? t('finance.editCategory') : t('finance.newCategory')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField select label={t('finance.kindLabel')} value={f.kind} disabled={Boolean(category)} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <MenuItem value="INCOME">{t('finance.kind.INCOME')}</MenuItem><MenuItem value="EXPENSE">{t('finance.kind.EXPENSE')}</MenuItem>
          </TextField>
          <TextField label={t('finance.code')} value={f.code} disabled={Boolean(category)} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_') })} />
          <TextField label={t('common.name')} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <TextField label={t('parish.nameLocal')} value={f.name_local} onChange={(e) => setF({ ...f, name_local: e.target.value })} />
          {category && <FormControlLabel control={<Switch checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />} label={t('finance.inUse')} />}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={f.name.trim().length < 2 || (!category && f.code.length < 2) || save.isPending} onClick={() => save.mutate()}>{t('common.save')}</Button>
      </DialogActions>
    </Dialog>
  );
}

export function AccountsPage() {
  const { t } = useTranslation();
  const can = useCan();
  const configure = can('finance.configure');
  const [tab, setTab] = useState<'accounts' | 'categories'>('accounts');
  const { data: accounts = [] } = useAccounts(true);
  const { data: categories = [] } = useCategories(true);
  const [editing, setEditing] = useState<FinAccount | null | undefined>(undefined);
  const [editingCat, setEditingCat] = useState<FinCategory | null | undefined>(undefined);
  const total = accounts.filter((a) => a.is_active && a.balance != null).reduce((s, a) => s + Number(a.balance), 0);
  return (
    <>
      <PageHeader
        title={t('nav.accounts')}
        subtitle={t('finance.accountsSubtitle')}
        breadcrumbs={[{ label: t('nav.finance') }, { label: t('nav.accounts') }]}
        actions={configure && (tab === 'accounts'
          ? <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing(null)}>{t('finance.newAccount')}</Button>
          : <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditingCat(null)}>{t('finance.newCategory')}</Button>)}
      />
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="accounts" label={t('finance.accountsTab')} />
        <Tab value="categories" label={t('finance.categoriesTab')} />
      </Tabs>
      {tab === 'accounts' ? (
        <Card sx={{ overflowX: 'auto' }}>
          <Table aria-label={t('finance.accountsTab')}>
            <TableHead>
              <TableRow>
                <TableCell>{t('finance.account')}</TableCell><TableCell>{t('activities.organisation')}</TableCell>
                <TableCell>{t('finance.openingDate')}</TableCell><TableCell align="right">{t('finance.balance')}</TableCell><TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {accounts.map((a) => (
                <TableRow key={a.id} sx={{ opacity: a.is_active ? 1 : 0.55 }}>
                  <TableCell>
                    <Typography variant="body2" fontWeight={600}>{a.name}</Typography>
                    <Typography variant="caption" color="text.secondary">{a.code} · {t(`finance.accountKinds.${a.kind}`)}{a.bank_name ? ` · ${a.bank_name}` : ''}{a.account_number_masked ? ` ${a.account_number_masked}` : ''}</Typography>
                  </TableCell>
                  <TableCell>{a.org_unit?.name ?? t('activities.parishLevel')}</TableCell>
                  <TableCell>{formatDate(a.opening_date)}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" fontWeight={600} sx={{ fontVariantNumeric: 'tabular-nums' }}>{a.balance != null ? inr(a.balance) : '—'}</Typography>
                    {a.pending > 0 && <Chip size="small" variant="outlined" color="warning" label={t('finance.pendingN', { count: a.pending })} />}
                  </TableCell>
                  <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                    <Button size="small" component={RouterLink} to={`/finance/transactions?account=${a.id}`}>{t('finance.entries')}</Button>
                    {configure && <IconButton aria-label={`${t('common.edit')} ${a.name}`} onClick={() => setEditing(a)}><EditIcon fontSize="small" /></IconButton>}
                  </TableCell>
                </TableRow>
              ))}
              <TableRow>
                <TableCell colSpan={3}><strong>{t('finance.totalActive')}</strong></TableCell>
                <TableCell align="right"><strong>{inr(total)}</strong></TableCell><TableCell />
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      ) : (
        <Grid container spacing={2}>
          {(['INCOME', 'EXPENSE'] as const).map((k) => (
            <Grid key={k} size={{ xs: 12, md: 6 }}>
              <Card>
                <Typography variant="h3" sx={{ p: 2, pb: 1 }}>{t(`finance.kind.${k}`)}</Typography>
                <Table size="small" aria-label={t(`finance.kind.${k}`)}>
                  <TableBody>
                    {categories.filter((c) => c.kind === k).map((c) => (
                      <TableRow key={c.id} sx={{ opacity: c.is_active ? 1 : 0.55 }}>
                        <TableCell><Typography variant="body2">{c.name}</Typography>{c.name_local && <Typography variant="caption" color="text.secondary">{c.name_local}</Typography>}</TableCell>
                        <TableCell><Typography variant="caption" color="text.secondary">{c.code}</Typography></TableCell>
                        <TableCell align="right">{configure && <IconButton size="small" aria-label={`${t('common.edit')} ${c.name}`} onClick={() => setEditingCat(c)}><EditIcon fontSize="small" /></IconButton>}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
      <AccountDialog open={editing !== undefined} onClose={() => setEditing(undefined)} account={editing ?? undefined} />
      <CategoryDialog open={editingCat !== undefined} onClose={() => setEditingCat(undefined)} category={editingCat ?? undefined} />
    </>
  );
}
