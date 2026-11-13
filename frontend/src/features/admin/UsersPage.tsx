import AddIcon from '@mui/icons-material/PersonAddAlt1Outlined';
import LockIcon from '@mui/icons-material/LockOutlined';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { UserOut } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, PageHeader, StatusBadge } from '@/design-system';
import { formatDateTime } from '@/lib/format';
import { useSearchParams } from 'react-router-dom';
import { fetchUsers, useRoles, type UserFilters } from './api';
import { CreateUserDialog } from './CreateUserDialog';
import { UserDrawer } from './UserDrawer';

export function UsersPage() {
  const { t } = useTranslation();
  const [q, setQ] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState<'all' | 'active' | 'inactive'>('all');
  const [search] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(search.get('open'));
  const [creating, setCreating] = useState(false);
  const deferredQ = useDeferredValue(q);
  const { data: roles } = useRoles();
  const filters: UserFilters = {
    q: deferredQ.trim() || undefined,
    role: role || undefined,
    is_active: status === 'all' ? undefined : status === 'active',
  };

  const columns: GridColDef<UserOut>[] = [
    {
      field: 'full_name',
      headerName: t('common.name'),
      flex: 1.2,
      minWidth: 180,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={1} alignItems="center" sx={{ height: '100%' }}>
          <span>{row.full_name}</span>
          {row.is_locked && (
            <Tooltip title={t('users.locked')}>
              <LockIcon fontSize="small" color="warning" />
            </Tooltip>
          )}
        </Stack>
      ),
    },
    { field: 'username', headerName: t('common.username'), flex: 0.8, minWidth: 130 },
    { field: 'email', headerName: t('common.email'), flex: 1, minWidth: 180, sortable: false },
    {
      field: 'roles',
      headerName: t('common.roles'),
      flex: 1.4,
      minWidth: 200,
      sortable: false,
      renderCell: ({ row }) => (
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ height: '100%', overflow: 'hidden' }}>
          {row.roles.map((r) => (
            <Chip key={r} size="small" variant="outlined" label={roles?.find((x) => x.code === r)?.name ?? r} />
          ))}
        </Stack>
      ),
    },
    {
      field: 'is_active',
      headerName: t('common.status'),
      width: 120,
      sortable: false,
      renderCell: ({ row }) => <StatusBadge status={row.is_active ? 'ACTIVE' : 'INACTIVE'} />,
    },
    {
      field: 'last_login_at',
      headerName: t('common.lastLogin'),
      width: 170,
      valueFormatter: (v: string | null) => (v ? formatDateTime(v) : t('common.never')),
    },
  ];

  return (
    <>
      <PageHeader
        title={t('users.title')}
        subtitle={t('users.subtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('users.title') }]}
        actions={
          <PermissionGate anyOf="user.create">
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreating(true)}>
              {t('users.new')}
            </Button>
          </PermissionGate>
        }
      />
      <DataTable<UserOut>
        queryKey={['users', 'list', filters]}
        fetchPage={(req) => fetchUsers(req, filters)}
        columns={columns}
        onRowClick={(u) => setSelected(u.id)}
        initialSort={[{ field: 'full_name', sort: 'asc' }]}
        toolbar={
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
            <TextField
              label={t('common.search')}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              sx={{ maxWidth: { sm: 320 } }}
            />
            <TextField select label={t('users.role')} value={role} onChange={(e) => setRole(e.target.value)}
              sx={{ minWidth: 200, maxWidth: { sm: 260 } }}>
              <MenuItem value="">{t('common.all')}</MenuItem>
              {(roles ?? []).map((r) => (
                <MenuItem key={r.code} value={r.code}>
                  {r.name}
                </MenuItem>
              ))}
            </TextField>
            <TextField select label={t('common.status')} value={status}
              onChange={(e) => setStatus(e.target.value as typeof status)} sx={{ minWidth: 150, maxWidth: { sm: 180 } }}>
              <MenuItem value="all">{t('common.all')}</MenuItem>
              <MenuItem value="active">{t('common.active')}</MenuItem>
              <MenuItem value="inactive">{t('common.inactive')}</MenuItem>
            </TextField>
          </Stack>
        }
      />
      <CreateUserDialog open={creating} onClose={() => setCreating(false)} onCreated={(id) => setSelected(id)} />
      <UserDrawer userId={selected} onClose={() => setSelected(null)} />
    </>
  );
}
