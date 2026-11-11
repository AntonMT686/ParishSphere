import CloseIcon from '@mui/icons-material/Close';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/api/client';
import type { FamilyListItem, Member } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { StatusBadge, useFeedback } from '@/design-system';
import { formatDate } from '@/lib/format';
import { peopleKeys, useFamily, useMember, useMemberMemberships } from './api';
import { RELATIONSHIPS, useLabels } from './labels';
import { MemberDialog } from './MemberDialog';
import { FamilyPicker } from './pickers';

function Row({ label, value }: { label: string; value?: string | number | null }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.4 }}>
      <Typography color="text.secondary" sx={{ width: 150, flexShrink: 0 }} variant="body2">{label}</Typography>
      <Typography variant="body2">{value}</Typography>
    </Stack>
  );
}

function sacrament(date?: string | null, place?: string | null, ref?: string | null) {
  if (!date && !place) return null;
  return [date && formatDate(date), place, ref && `#${ref}`].filter(Boolean).join(' · ');
}

export function MemberDrawer({ memberId, onClose }: { memberId: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const L = useLabels();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError, confirm } = useFeedback();
  const { data: m } = useMember(memberId);
  const { data: memberships } = useMemberMemberships(memberId);
  const { data: family } = useFamily(m?.family.id ?? '');
  const [editing, setEditing] = useState(false);
  const [dialog, setDialog] = useState<'deceased' | 'move' | null>(null);
  const [dod, setDod] = useState('');
  const [remarks, setRemarks] = useState('');
  const [target, setTarget] = useState<FamilyListItem | null>(null);
  const [rel, setRel] = useState('OTHER');
  const [newHead, setNewHead] = useState('');

  const act = useMutation({
    mutationFn: async ({ path, body, method = 'post' }: { path: string; body?: unknown; method?: 'post' | 'delete' }) =>
      (await api.request<Member>({ url: `/members/${memberId}${path}`, method, data: body })).data,
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: peopleKeys.families });
      void qc.invalidateQueries({ queryKey: peopleKeys.members });
      toast(t('common.saved'));
      setDialog(null);
      if (v.method === 'delete') onClose();
    },
    onError: toastError,
  });

  const remaining = (family?.members ?? []).filter((x) => x.status === 'ACTIVE' && x.id !== m?.id);
  const canUpdate = can('member.update');

  return (
    <Drawer anchor="right" open={Boolean(memberId)} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 520 } } }}>
      {m && (
        <Box sx={{ p: 3 }}>
          <Stack direction="row" alignItems="flex-start">
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="h3">{m.full_name}</Typography>
              {m.name_local && <Typography color="text.secondary">{m.name_local}</Typography>}
              <Typography variant="body2" color="text.secondary">
                {m.code} · <RouterLink to={`/families/${m.family.id}`}>{m.family.name}</RouterLink>
              </Typography>
            </Box>
            <IconButton aria-label={t('common.close')} onClick={onClose}><CloseIcon /></IconButton>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ my: 2 }} flexWrap="wrap" useFlexGap>
            <StatusBadge status={m.status} />
            {m.is_head && <Chip size="small" color="primary" label={t('people.head')} />}
            <Chip size="small" variant="outlined" label={L.rel(m.relationship_to_head)} />
          </Stack>
          <Row label={t('people.genderLabel')} value={L.gender(m.gender)} />
          <Row label={t('people.age')} value={m.age} />
          <Row label={t('nav.anbiyam')} value={m.anbiyam?.name} />
          <Row label={t('people.dateOfDeath')} value={m.date_of_death ? formatDate(m.date_of_death) : null} />
          {m.sensitive_visible ? (
            <>
              <Row label={t('people.dob')} value={m.date_of_birth ? formatDate(m.date_of_birth) : null} />
              <Row label={t('common.phone')} value={m.phone} />
              <Row label={t('common.email')} value={m.email} />
              <Row label={t('people.maritalStatus')} value={m.marital_status ? L.marital(m.marital_status) : null} />
              <Row label={t('people.education')} value={m.education} />
              <Row label={t('people.occupation')} value={m.occupation} />
              <Row label={t('people.remarks')} value={m.remarks} />
            </>
          ) : (
            <Alert severity="info" sx={{ my: 1 }}>{t('people.sensitiveHidden')}</Alert>
          )}
          {m.sacraments_visible && (
            <>
              <Divider sx={{ my: 1.5 }}><Typography variant="caption">{t('people.sacraments')}</Typography></Divider>
              <Row label={t('people.baptismDate')} value={sacrament(m.baptism_date, m.baptism_place, m.baptism_register_ref)} />
              <Row label={t('people.communionDate')} value={sacrament(m.communion_date, m.communion_place)} />
              <Row label={t('people.confirmationDate')} value={sacrament(m.confirmation_date, m.confirmation_place)} />
              <Row label={t('people.marriageDate')} value={sacrament(m.marriage_date, m.marriage_place, m.marriage_register_ref)} />
            </>
          )}
          <Divider sx={{ my: 2 }} />
          <Typography variant="h4" gutterBottom>{t('people.memberships')}</Typography>
          <List dense disablePadding>
            {(memberships ?? []).length === 0 && <Typography color="text.secondary" variant="body2">{t('common.noRecords')}</Typography>}
            {(memberships ?? []).map((ms) => (
              <ListItem key={`${ms.org_unit.id}-${ms.id}`} disableGutters>
                <ListItemText primary={ms.org_unit.name} secondary={ms.joined_on ? `${t('users.validFrom')} ${formatDate(ms.joined_on)}` : t('people.viaFamily')} />
              </ListItem>
            ))}
          </List>
          {canUpdate && m.status !== 'DECEASED' && m.status !== 'TRANSFERRED_OUT' && (
            <>
              <Divider sx={{ my: 2 }} />
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button variant="contained" onClick={() => setEditing(true)}>{t('common.edit')}</Button>
                {can('family.transfer') && m.status === 'ACTIVE' && <Button onClick={() => setDialog('move')}>{t('people.moveFamily')}</Button>}
                {m.status === 'ACTIVE' && <Button onClick={() => { setDod(new Date().toISOString().slice(0, 10)); setRemarks(''); setDialog('deceased'); }}>{t('people.markDeceased')}</Button>}
                <Button onClick={() => act.mutate({ path: '/status', body: { active: m.status !== 'ACTIVE' } })}>
                  {m.status === 'ACTIVE' ? t('users.deactivate') : t('users.activate')}
                </Button>
                {can('member.delete') && !m.is_head && (
                  <Button color="error" onClick={async () => {
                    if (await confirm({ title: t('common.delete'), message: t('people.deleteMemberConfirm'), destructive: true })) {
                      act.mutate({ path: '', method: 'delete' });
                    }
                  }}>{t('common.delete')}</Button>
                )}
              </Stack>
            </>
          )}
          <MemberDialog open={editing} onClose={() => setEditing(false)} member={m} />
          <Dialog open={dialog === 'deceased'} onClose={() => setDialog(null)} maxWidth="xs" fullWidth>
            <DialogTitle>{t('people.markDeceased')}</DialogTitle>
            <DialogContent>
              <Stack spacing={2} sx={{ pt: 1 }}>
                {m.is_head && <Alert severity="warning">{t('people.headDeceasedHint')}</Alert>}
                <TextField label={t('people.dateOfDeath')} type="date" value={dod} onChange={(e) => setDod(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
                <TextField label={t('people.remarks')} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDialog(null)}>{t('common.cancel')}</Button>
              <Button variant="contained" disabled={!dod || act.isPending} onClick={() => act.mutate({ path: '/deceased', body: { date_of_death: dod, remarks: remarks || null } })}>{t('common.save')}</Button>
            </DialogActions>
          </Dialog>
          <Dialog open={dialog === 'move'} onClose={() => setDialog(null)} maxWidth="sm" fullWidth>
            <DialogTitle>{t('people.moveFamily')}</DialogTitle>
            <DialogContent>
              <Stack spacing={2} sx={{ pt: 1 }}>
                <FamilyPicker label={t('people.toFamily')} value={target} onChange={setTarget} excludeId={m.family.id} />
                <TextField select label={t('people.relationship')} value={rel} onChange={(e) => setRel(e.target.value)}>
                  {RELATIONSHIPS.map((r) => <MenuItem key={r} value={r}>{L.rel(r)}</MenuItem>)}
                </TextField>
                {m.is_head && remaining.length > 0 && (
                  <TextField select label={t('people.remainingHead')} value={newHead} onChange={(e) => setNewHead(e.target.value)}>
                    {remaining.map((x) => <MenuItem key={x.id} value={x.id}>{x.full_name}</MenuItem>)}
                  </TextField>
                )}
              </Stack>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setDialog(null)}>{t('common.cancel')}</Button>
              <Button variant="contained" disabled={!target || (m.is_head && remaining.length > 0 && !newHead) || act.isPending}
                onClick={() => act.mutate({ path: '/move', body: { family_id: target?.id, relationship_to_head: rel, new_head_member_id: newHead || null } })}>
                {t('people.moveFamily')}
              </Button>
            </DialogActions>
          </Dialog>
        </Box>
      )}
    </Drawer>
  );
}
