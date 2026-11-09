import CloseIcon from '@mui/icons-material/Close';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '@/api/client';
import { useAuthStore, useCan } from '@/auth/authStore';
import { StatusBadge, useFeedback } from '@/design-system';
import { formatDate, formatDateTime } from '@/lib/format';
import { OrgUnitPicker } from '@/features/org/pickers';
import { useRoles, useUser, useUserRoles } from './api';

export function UserDrawer({ userId, onClose }: { userId: string | null; onClose: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const can = useCan();
  const me = useAuthStore((s) => s.user);
  const { toast, toastError, confirm } = useFeedback();
  const { data: user } = useUser(userId);
  const [history, setHistory] = useState(false);
  const { data: assignments } = useUserRoles(userId, history);
  const { data: roles } = useRoles(Boolean(userId));
  const [edit, setEdit] = useState({ full_name: '', email: '', phone: '' });
  const [newRole, setNewRole] = useState('');
  const [newRoleUnit, setNewRoleUnit] = useState<{ id: string; name: string; code: string } | null>(null);
  const isSelf = me?.id === userId;

  useEffect(() => {
    if (user) setEdit({ full_name: user.full_name, email: user.email ?? '', phone: user.phone ?? '' });
  }, [user]);

  const refresh = () => qc.invalidateQueries({ queryKey: ['users'] });
  const action = useMutation({
    mutationFn: async ({ path, method = 'post', body }: { path: string; method?: 'post' | 'patch' | 'delete'; body?: unknown }) =>
      api.request({ url: `/users/${userId}${path}`, method, data: body }),
    onSuccess: () => {
      toast(t('common.saved'));
      void refresh();
    },
    onError: toastError,
  });

  const run = async (path: string, opts: { method?: 'post' | 'patch' | 'delete'; body?: unknown; confirmText?: string; destructive?: boolean } = {}) => {
    if (opts.confirmText && !(await confirm({ title: t('common.confirm'), message: opts.confirmText, destructive: opts.destructive }))) return;
    await action.mutateAsync({ path, method: opts.method, body: opts.body });
  };

  const assignable = roles ?? [];
  const newRoleScope = assignable.find((r) => r.code === newRole)?.scope_type;
  const needsUnit = newRoleScope === 'ORG_UNIT';

  return (
    <Drawer anchor="right" open={Boolean(userId)} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 480 } } }}>
      {user && (
        <Box sx={{ p: 3 }}>
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <Box sx={{ flexGrow: 1 }}>
              <Typography variant="h3">{user.full_name}</Typography>
              <Typography color="text.secondary">@{user.username}</Typography>
            </Box>
            <IconButton aria-label={t('common.close')} onClick={onClose}>
              <CloseIcon />
            </IconButton>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ my: 2 }} flexWrap="wrap" useFlexGap>
            <StatusBadge status={user.is_active ? 'ACTIVE' : 'INACTIVE'} />
            {user.is_locked && <Chip size="small" color="warning" label={t('users.locked')} />}
            {user.must_change_password && <Chip size="small" variant="outlined" label={t('users.mustChange')} />}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {t('common.lastLogin')}: {user.last_login_at ? formatDateTime(user.last_login_at) : t('common.never')}
          </Typography>

          {can('user.update') && (
            <>
              <Divider sx={{ my: 2 }} />
              <Stack spacing={2}>
                <TextField label={t('users.fullName')} value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} />
                <TextField label={t('common.email')} value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} />
                <TextField label={t('common.phone')} value={edit.phone} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} />
                <Box>
                  <Button variant="contained" onClick={() => void run('', { method: 'patch', body: { full_name: edit.full_name, email: edit.email || null, phone: edit.phone || null } })}>
                    {t('common.save')}
                  </Button>
                </Box>
              </Stack>
              <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
                {!isSelf &&
                  (user.is_active ? (
                    <Button color="warning" onClick={() => void run('/deactivate', { confirmText: t('users.deactivateConfirm'), destructive: true })}>
                      {t('users.deactivate')}
                    </Button>
                  ) : (
                    <Button onClick={() => void run('/activate')}>{t('users.activate')}</Button>
                  ))}
                {user.is_locked && <Button onClick={() => void run('/unlock')}>{t('users.unlock')}</Button>}
                {user.email && <Button onClick={() => void run('/send-password-reset')}>{t('users.sendReset')}</Button>}
              </Stack>
            </>
          )}

          <Divider sx={{ my: 2 }} />
          <Stack direction="row" alignItems="center">
            <Typography variant="h4" sx={{ flexGrow: 1 }}>
              {t('common.roles')}
            </Typography>
            <FormControlLabel control={<Switch size="small" checked={history} onChange={(_, v) => setHistory(v)} />} label={t('users.history')} />
          </Stack>
          {isSelf && <Alert severity="info" sx={{ my: 1 }}>{t('errors.SELF_MODIFICATION')}</Alert>}
          <List dense>
            {(assignments ?? []).length === 0 && <Typography color="text.secondary">{t('users.noRoles')}</Typography>}
            {(assignments ?? []).map((a) => (
              <ListItem
                key={a.id}
                disableGutters
                secondaryAction={
                  a.active && can('user.assign_role') && !isSelf ? (
                    <Button size="small" color="error" onClick={() => void run(`/roles/${a.id}`, { method: 'delete', confirmText: `${t('users.endRole')}: ${a.role_name}?` })}>
                      {t('users.endRole')}
                    </Button>
                  ) : !a.active ? (
                    <Chip size="small" label={t('users.ended')} />
                  ) : undefined
                }
              >
                <ListItemText
                  primary={a.org_unit_id ? `${a.role_name} · ${t('org.scoped')}` : a.role_name}
                  secondary={`${t('users.validFrom')} ${formatDate(a.valid_from)}${a.valid_to ? ` · ${t('users.validTo')} ${formatDate(a.valid_to)}` : ''}${a.ended_at ? ` · ${t('users.ended')} ${formatDate(a.ended_at)}` : ''}`}
                  sx={{ opacity: a.active ? 1 : 0.6 }}
                />
              </ListItem>
            ))}
          </List>
          {can('user.assign_role') && !isSelf && (
            <Stack spacing={1} sx={{ mt: 1 }}>
              <TextField select label={t('users.addRole')} value={newRole} onChange={(e) => { setNewRole(e.target.value); setNewRoleUnit(null); }}>
                {assignable.map((r) => (
                  <MenuItem key={r.code} value={r.code}>
                    {r.name}
                    {r.scope_type === 'ORG_UNIT' ? ` · ${t('roles.scope_ORG_UNIT')}` : ''}
                  </MenuItem>
                ))}
              </TextField>
              {newRoleScope && newRoleScope !== 'PARISH' && (
                <OrgUnitPicker
                  label={needsUnit ? t('org.forOrganisation') : t('org.forOrganisationOptional')}
                  value={newRoleUnit}
                  onChange={setNewRoleUnit}
                />
              )}
              <Box>
                <Button
                  variant="outlined"
                  disabled={!newRole || (needsUnit && !newRoleUnit)}
                  onClick={async () => {
                    await run('/roles', { body: { role_code: newRole, org_unit_id: newRoleUnit?.id ?? null } });
                    setNewRole('');
                    setNewRoleUnit(null);
                  }}
                >
                  {t('users.addRole')}
                </Button>
              </Box>
            </Stack>
          )}

          {can('user.delete') && !isSelf && (
            <>
              <Divider sx={{ my: 2 }} />
              <Button
                color="error"
                startIcon={<DeleteIcon />}
                onClick={async () => {
                  if (await confirm({ title: t('common.delete'), message: t('users.deleteConfirm'), destructive: true })) {
                    try {
                      await api.delete(`/users/${userId}`);
                      toast(t('common.saved'));
                      void refresh();
                      onClose();
                    } catch (e) {
                      toastError(e);
                    }
                  }
                }}
              >
                {t('common.delete')}
              </Button>
            </>
          )}
        </Box>
      )}
    </Drawer>
  );
}
