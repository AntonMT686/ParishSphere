import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import type { OrgUnitType } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { useRoles } from '@/features/admin/api';
import { orgKeys, useOrgTypes } from './api';

function RoleSelect({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const { t } = useTranslation();
  const { data: roles } = useRoles();
  return (
    <TextField
      select
      size="small"
      label={label || undefined}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      sx={{ minWidth: 180 }}
      slotProps={{
        select: { displayEmpty: true, renderValue: (v) => (roles ?? []).find((r) => r.code === v)?.name ?? t('org.noRole') },
        inputLabel: { shrink: true },
      }}
    >
      <MenuItem value="">{t('org.noRole')}</MenuItem>
      {(roles ?? []).map((r) => (
        <MenuItem key={r.code} value={r.code}>{r.name}</MenuItem>
      ))}
    </TextField>
  );
}

function TypeCard({ type }: { type: OrgUnitType }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const editable = can('org_unit.update');
  const { toast, toastError, confirm } = useFeedback();
  const [newPos, setNewPos] = useState({ code: '', name: '', role_code: '', max_holders: '1' });
  const refresh = () => qc.invalidateQueries({ queryKey: orgKeys.types });
  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      toast(t('common.saved'));
      void refresh();
    } catch (e) {
      toastError(e);
    }
  };
  const addPosition = useMutation({
    mutationFn: () =>
      api.post(`/org-unit-types/${type.id}/positions`, {
        code: newPos.code, name: newPos.name, role_code: newPos.role_code || null,
        max_holders: newPos.max_holders ? Number(newPos.max_holders) : null,
      }),
    onSuccess: () => {
      setNewPos({ code: '', name: '', role_code: '', max_holders: '1' });
      toast(t('common.saved'));
      void refresh();
    },
    onError: toastError,
  });
  return (
    <Card>
      <CardHeader
        title={type.name_plural}
        subheader={`${type.code} · ${type.member_kind === 'FAMILY' ? t('org.familiesJoin') : t('org.membersJoin')} · ${type.unit_count} ${t('org.units')}`}
        action={
          <Stack direction="row" spacing={1} alignItems="center">
            {type.is_system && <Chip size="small" label={t('roles.system')} />}
            {!type.allow_multiple_units && <Chip size="small" variant="outlined" label={t('org.singleUnit')} />}
            {editable && !type.is_system && (
              <IconButton aria-label={t('common.delete')} onClick={async () => {
                if (await confirm({ title: t('common.delete'), message: type.name_plural, destructive: true })) {
                  await run(() => api.delete(`/org-unit-types/${type.id}`));
                }
              }}><DeleteIcon /></IconButton>
            )}
          </Stack>
        }
      />
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>{t('org.position')}</TableCell>
            <TableCell>{t('org.grantsRoleCol')}</TableCell>
            <TableCell align="right">{t('org.maxHolders')}</TableCell>
            {editable && <TableCell />}
          </TableRow>
        </TableHead>
        <TableBody>
          {type.positions.map((p) => (
            <TableRow key={p.id}>
              <TableCell>{p.name}{p.name_local ? ` · ${p.name_local}` : ''}</TableCell>
              <TableCell>
                {editable ? (
                  <RoleSelect label="" value={p.role_code ?? ''}
                    onChange={(v) => void run(() => api.patch(`/org-unit-types/${type.id}/positions/${p.id}`, { role_code: v || null }))} />
                ) : (p.role_name ?? '—')}
              </TableCell>
              <TableCell align="right">{p.max_holders ?? '∞'}</TableCell>
              {editable && (
                <TableCell align="right">
                  <IconButton size="small" aria-label={`${t('common.delete')} ${p.name}`}
                    onClick={() => void run(() => api.delete(`/org-unit-types/${type.id}/positions/${p.id}`))}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {editable && (
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
            <TextField size="small" label={t('org.code')} value={newPos.code} onChange={(e) => setNewPos({ ...newPos, code: e.target.value.toUpperCase() })} />
            <TextField size="small" label={t('common.name')} value={newPos.name} onChange={(e) => setNewPos({ ...newPos, name: e.target.value })} />
            <RoleSelect label={t('org.grantsRoleCol')} value={newPos.role_code} onChange={(v) => setNewPos({ ...newPos, role_code: v })} />
            <TextField size="small" type="number" label={t('org.maxHolders')} value={newPos.max_holders}
              onChange={(e) => setNewPos({ ...newPos, max_holders: e.target.value })} sx={{ minWidth: 120, maxWidth: { md: 130 } }}
              helperText={t('org.maxHoldersHint')} />
            <Button startIcon={<AddIcon />} sx={{ whiteSpace: 'nowrap', flexShrink: 0, alignSelf: { md: 'flex-start' } }} disabled={!newPos.code || !newPos.name || addPosition.isPending} onClick={() => addPosition.mutate()}>
              {t('org.addPosition')}
            </Button>
          </Stack>
        </CardContent>
      )}
    </Card>
  );
}

function CreateTypeDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toastError } = useFeedback();
  const empty = { code: '', name: '', name_plural: '', name_local: '', code_prefix: '', member_kind: 'MEMBER', allow_multiple_units: true };
  const [v, setV] = useState(empty);
  const create = useMutation({
    mutationFn: () => api.post('/org-unit-types', { ...v, name_local: v.name_local || null }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: orgKeys.types });
      setV(empty);
      onClose();
    },
    onError: toastError,
  });
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('org.newType')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Stack direction="row" spacing={2}>
            <TextField label={t('common.name')} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} placeholder="Zone" />
            <TextField label={t('org.plural')} value={v.name_plural} onChange={(e) => setV({ ...v, name_plural: e.target.value })} placeholder="Zones" />
          </Stack>
          <TextField label={t('org.nameLocal')} value={v.name_local} onChange={(e) => setV({ ...v, name_local: e.target.value })} />
          <Stack direction="row" spacing={2}>
            <TextField label={t('org.code')} value={v.code} onChange={(e) => setV({ ...v, code: e.target.value.toUpperCase() })} />
            <TextField label={t('org.codePrefix')} value={v.code_prefix} onChange={(e) => setV({ ...v, code_prefix: e.target.value.toUpperCase() })} />
          </Stack>
          <TextField select label={t('org.whoJoins')} value={v.member_kind} onChange={(e) => setV({ ...v, member_kind: e.target.value })}>
            <MenuItem value="MEMBER">{t('org.membersJoin')}</MenuItem>
            <MenuItem value="FAMILY">{t('org.familiesJoin')}</MenuItem>
          </TextField>
          <FormControlLabel control={<Switch checked={v.allow_multiple_units} onChange={(_, x) => setV({ ...v, allow_multiple_units: x })} />}
            label={t('org.allowMultiple')} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="contained" onClick={() => create.mutate()} disabled={!v.code || !v.name || !v.name_plural || !v.code_prefix || create.isPending}>
          {t('common.create')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function OrgTypesPage() {
  const { t } = useTranslation();
  const can = useCan();
  const { data } = useOrgTypes();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader
        title={t('nav.orgTypes')}
        subtitle={t('org.typesSubtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.orgTypes') }]}
        actions={can('org_unit.create') && <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreating(true)}>{t('org.newType')}</Button>}
      />
      <Grid container spacing={2}>
        {(data ?? []).map((type) => (
          <Grid key={type.id} size={{ xs: 12, xl: 6 }}>
            <TypeCard type={type} />
          </Grid>
        ))}
      </Grid>
      <CreateTypeDialog open={creating} onClose={() => setCreating(false)} />
    </>
  );
}
