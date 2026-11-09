import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { OrgPosition, OrgUnit, UserLookup } from '@/api/types';
import { useFeedback } from '@/design-system';
import { orgKeys } from './api';
import { UserPicker } from './pickers';

export function AppointDialog({ open, onClose, unit, positions }: {
  open: boolean;
  onClose: () => void;
  unit: OrgUnit;
  positions: OrgPosition[];
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const [position, setPosition] = useState('');
  const [user, setUser] = useState<UserLookup | null>(null);
  const [holderName, setHolderName] = useState('');
  const [validFrom, setValidFrom] = useState('');
  const [validTo, setValidTo] = useState('');
  useEffect(() => {
    if (open) {
      setPosition(positions[0]?.code ?? '');
      setUser(null);
      setHolderName('');
      setValidFrom(new Date().toISOString().slice(0, 10));
      setValidTo('');
    }
  }, [open, positions]);
  const selected = positions.find((p) => p.code === position);
  const appoint = useMutation({
    mutationFn: () =>
      api.post(`/org-units/${unit.id}/office-bearers`, {
        position_code: position,
        user_id: user?.id ?? null,
        holder_name: user ? null : holderName || null,
        valid_from: validFrom || null,
        valid_to: validTo || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: orgKeys.units });
      toast(t('common.saved'));
      onClose();
    },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('org.appoint')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <TextField select label={t('org.position')} value={position} onChange={(e) => setPosition(e.target.value)}>
            {positions.map((p) => (
              <MenuItem key={p.code} value={p.code}>
                {p.name}
                {p.role_name ? ` — ${p.role_name}` : ''}
              </MenuItem>
            ))}
          </TextField>
          <UserPicker label={t('org.person')} value={user} onChange={setUser} />
          {!user && (
            <TextField label={t('org.holderName')} value={holderName} onChange={(e) => setHolderName(e.target.value)}
              helperText={t('org.holderNameHint')} />
          )}
          {selected?.role_name && (
            <Alert severity={user ? 'info' : 'warning'}>
              {user ? t('org.grantsRole', { role: selected.role_name }) : t('org.noLoginNoRole', { role: selected.role_name })}
            </Alert>
          )}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField label={t('users.validFrom')} type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} />
            <TextField label={t('users.validTo')} type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }} helperText={t('org.openEnded')} />
          </Stack>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" disabled={!position || (!user && !holderName.trim()) || appoint.isPending}
          onClick={() => appoint.mutate()}>
          {t('org.appoint')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
