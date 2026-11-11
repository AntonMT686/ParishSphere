import AddIcon from '@mui/icons-material/PersonAddAlt1Outlined';
import EditIcon from '@mui/icons-material/EditOutlined';
import MoreIcon from '@mui/icons-material/MoreVert';
import StarIcon from '@mui/icons-material/Star';
import TimelineIcon from '@mui/icons-material/TimelineOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid2';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import { useCan } from '@/auth/authStore';
import { PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { NotFoundPage } from '@/features/NotFoundPage';
import { formatDate } from '@/lib/format';
import { peopleKeys, useFamily, useFamilyHistory } from './api';
import { FamilyDialogs, type FamilyAction } from './FamilyDialogs';
import { useLabels } from './labels';
import { MemberDialog } from './MemberDialog';
import { MemberDrawer } from './MemberDrawer';

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.5 }}>
      <Typography color="text.secondary" sx={{ width: 140, flexShrink: 0 }}>{label}</Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap' }}>{value}</Typography>
    </Stack>
  );
}

export function FamilyDetailPage() {
  const { t } = useTranslation();
  const L = useLabels();
  const can = useCan();
  const qc = useQueryClient();
  const { toastError } = useFeedback();
  const { familyId = '' } = useParams();
  const { data: f, isError } = useFamily(familyId);
  const { data: history } = useFamilyHistory(familyId);
  const [action, setAction] = useState<FamilyAction>(null);
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [adding, setAdding] = useState(false);
  const [memberId, setMemberId] = useState<string | null>(null);
  const status = useMutation({
    mutationFn: (active: boolean) => api.post(`/families/${familyId}/status`, { active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: peopleKeys.families }),
    onError: toastError,
  });
  if (isError) return <NotFoundPage />;
  if (!f) return <Skeleton variant="rounded" height={360} />;
  const open = !['MERGED', 'TRANSFERRED_OUT'].includes(f.status);
  const address = [f.address_line1, f.address_line2, [f.city, f.state, f.postal_code].filter(Boolean).join(' ')].filter(Boolean).join('\n');
  const menuItem = (a: FamilyAction, label: string, perm: string) =>
    can(perm) && <MenuItem onClick={() => { setMenu(null); setAction(a); }}>{label}</MenuItem>;

  return (
    <>
      <PageHeader
        title={f.family_name}
        subtitle={f.family_name_local ?? undefined}
        breadcrumbs={[{ label: t('nav.families'), to: '/families' }, { label: f.family_name }]}
        actions={open && (
          <>
            {can('member.create') && <Button startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('people.addMember')}</Button>}
            {can('family.update') && <Button startIcon={<EditIcon />} onClick={() => setAction('edit')}>{t('common.edit')}</Button>}
            {(can('family.transfer') || can('family.update')) && (
              <Button variant="contained" endIcon={<MoreIcon />} onClick={(e) => setMenu(e.currentTarget)}>{t('common.actions')}</Button>
            )}
            <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}>
              {menuItem('anbiyam', t('people.changeAnbiyam'), 'family.transfer')}
              {menuItem('head', t('people.setHead'), 'family.update')}
              {menuItem('split', t('people.split'), 'family.transfer')}
              {menuItem('merge', t('people.merge'), 'family.transfer')}
              {menuItem('transfer', t('people.transferOut'), 'family.transfer')}
              {can('family.update') && (
                <MenuItem onClick={() => { setMenu(null); status.mutate(f.status === 'INACTIVE'); }}>
                  {f.status === 'INACTIVE' ? t('users.activate') : t('users.deactivate')}
                </MenuItem>
              )}
            </Menu>
          </>
        )}
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Chip label={f.code} />
        <StatusBadge status={f.status} size="medium" />
        {f.anbiyam ? (
          <Chip variant="outlined" label={f.anbiyam.name} component={RouterLink} to={`/org/units/${f.anbiyam.id}`} clickable />
        ) : (
          <Chip color="warning" variant="outlined" label={t('people.noAnbiyam')} />
        )}
      </Stack>
      {f.merged_into && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('people.mergedInto')} <RouterLink to={`/families/${f.merged_into.id}`}>{f.merged_into.code} · {f.merged_into.name}</RouterLink>
        </Alert>
      )}
      {open && !f.head_member_id && f.member_count > 0 && <Alert severity="warning" sx={{ mb: 2 }}>{t('people.noHeadWarning')}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Card>
            <CardHeader title={t('nav.members')} subheader={t('people.activeCount', { n: f.member_count })} />
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('common.name')}</TableCell>
                  <TableCell>{t('people.relationship')}</TableCell>
                  <TableCell>{t('people.genderLabel')}</TableCell>
                  <TableCell align="right">{t('people.age')}</TableCell>
                  <TableCell>{t('common.status')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {f.members.map((m) => (
                  <TableRow key={m.id} hover sx={{ cursor: 'pointer', opacity: m.status === 'ACTIVE' ? 1 : 0.6 }} onClick={() => setMemberId(m.id)}>
                    <TableCell>
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        {m.is_head && <StarIcon fontSize="small" color="secondary" titleAccess={t('people.head')} />}
                        <span><strong>{m.full_name}</strong>{m.name_local ? ` · ${m.name_local}` : ''}</span>
                      </Stack>
                      <Typography variant="caption" color="text.secondary">{m.code}</Typography>
                    </TableCell>
                    <TableCell>{L.rel(m.relationship_to_head)}</TableCell>
                    <TableCell>{L.gender(m.gender)}</TableCell>
                    <TableCell align="right">{m.age ?? '—'}</TableCell>
                    <TableCell><StatusBadge status={m.status} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Card sx={{ mb: 2 }}>
            <CardHeader title={t('org.details')} />
            <CardContent sx={{ pt: 0 }}>
              <Field label={t('common.phone')} value={f.phone} />
              <Field label={t('common.email')} value={f.email} />
              <Field label={t('people.address')} value={address} />
              <Field label={t('people.registered')} value={formatDate(f.registered_on)} />
              <Field label={t('people.previousParish')} value={[f.previous_parish, f.previous_diocese].filter(Boolean).join(', ')} />
              <Field label={t('people.remarks')} value={f.remarks} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader title={t('people.history')} />
            <List dense>
              {(history?.events ?? []).map((e, i) => (
                <ListItem key={i} alignItems="flex-start">
                  <ListItemIcon sx={{ minWidth: 32, mt: 0.5 }}><TimelineIcon fontSize="small" color="primary" /></ListItemIcon>
                  <ListItemText
                    primary={L.event(e.event_type)}
                    secondary={[formatDate(e.occurred_on), e.member?.name, e.related_family?.name,
                      (e.details as Record<string, string | null>).to_anbiyam, (e.details as Record<string, string | null>).reason,
                      e.performed_by].filter(Boolean).join(' · ')}
                  />
                </ListItem>
              ))}
            </List>
          </Card>
        </Grid>
      </Grid>
      <FamilyDialogs family={f} action={action} onClose={() => setAction(null)} />
      <MemberDialog open={adding} onClose={() => setAdding(false)} familyId={f.id} />
      <MemberDrawer memberId={memberId} onClose={() => setMemberId(null)} />
    </>
  );
}
