import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/EditOutlined';
import BadgeIcon from '@mui/icons-material/BadgeOutlined';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api, type Page } from '@/api/client';
import type { OrgUnit } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { formatDate } from '@/lib/format';
import { orgKeys, typePath, useBearers, useOrgTypes, useUnit } from './api';
import { AppointDialog } from './AppointDialog';
import { OrgUnitDialog } from './OrgUnitDialog';

function Field({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <Stack direction="row" spacing={2} sx={{ py: 0.5 }}>
      <Typography color="text.secondary" sx={{ width: 150, flexShrink: 0 }}>{label}</Typography>
      <Typography sx={{ whiteSpace: 'pre-wrap' }}>{value}</Typography>
    </Stack>
  );
}

export function OrgUnitDetailPage() {
  const { t } = useTranslation();
  const { unitId = '' } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useCan();
  const { toast, toastError, confirm } = useFeedback();
  const { data: unit, isError } = useUnit(unitId);
  const { data: types } = useOrgTypes();
  const [history, setHistory] = useState(false);
  const { data: bearers } = useBearers(unitId, history);
  const { data: children } = useQuery({
    queryKey: [...orgKeys.units, 'children', unitId],
    queryFn: async () => (await api.get<Page<OrgUnit>>('/org-units', { params: { parent: unitId, size: 100 } })).data.items,
  });
  const [editing, setEditing] = useState(false);
  const [appointing, setAppointing] = useState(false);
  const [addingChild, setAddingChild] = useState(false);

  if (isError) return <Typography color="text.secondary">{t('common.noRecords')}</Typography>;
  if (!unit) return <Skeleton variant="rounded" height={320} />;
  const type = types?.find((x) => x.code === unit.type_code);
  const refresh = () => qc.invalidateQueries({ queryKey: orgKeys.units });

  const setStatus = async (archive: boolean) => {
    if (archive && !(await confirm({ title: t('org.archive'), message: t('org.archiveConfirm'), destructive: true }))) return;
    try {
      await api.post(`/org-units/${unit.id}/${archive ? 'archive' : 'activate'}`);
      toast(t('common.saved'));
      void refresh();
    } catch (e) {
      toastError(e);
    }
  };
  const endTerm = async (bearerId: string, name: string) => {
    if (!(await confirm({ title: t('org.endTerm'), message: t('org.endTermConfirm', { name }) }))) return;
    try {
      await api.post(`/org-units/${unit.id}/office-bearers/${bearerId}/end`, {});
      toast(t('common.saved'));
      void refresh();
    } catch (e) {
      toastError(e);
    }
  };

  return (
    <>
      <PageHeader
        title={unit.name}
        subtitle={unit.name_local ?? undefined}
        breadcrumbs={[
          { label: t('nav.organisations') },
          { label: type?.name_plural ?? unit.type_name, to: typePath(unit.type_code) },
          { label: unit.name },
        ]}
        actions={
          <>
            {can('org_unit.update') && <Button startIcon={<EditIcon />} onClick={() => setEditing(true)}>{t('common.edit')}</Button>}
            {can('org_unit.delete') &&
              (unit.status === 'ACTIVE' ? (
                <Button color="warning" onClick={() => void setStatus(true)}>{t('org.archive')}</Button>
              ) : (
                <Button onClick={() => void setStatus(false)}>{t('users.activate')}</Button>
              ))}
          </>
        }
      />
      <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Chip label={unit.code} />
        <Chip label={unit.type_name} variant="outlined" />
        <StatusBadge status={unit.status} size="medium" />
      </Stack>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card sx={{ height: '100%' }}>
            <CardHeader title={t('org.details')} />
            <CardContent sx={{ pt: 0 }}>
              <Field label={t('org.parent')} value={unit.parent?.name} />
              <Field label={t('org.established')} value={unit.established_on ? formatDate(unit.established_on) : null} />
              <Field label={t('org.meetingPlace')} value={unit.meeting_place} />
              <Field label={t('org.meetingSchedule')} value={unit.meeting_schedule} />
              <Field label={t('common.phone')} value={unit.contact_phone} />
              <Field label={t('common.email')} value={unit.contact_email} />
              <Field label={t('roles.description')} value={unit.description} />
            </CardContent>
          </Card>
        </Grid>
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card sx={{ height: '100%' }}>
            <CardHeader
              title={t('org.officeBearers')}
              action={
                <Stack direction="row" spacing={1} alignItems="center">
                  <FormControlLabel control={<Switch size="small" checked={history} onChange={(_, v) => setHistory(v)} />} label={t('users.history')} />
                  {unit.can_manage && unit.status === 'ACTIVE' && (
                    <Button startIcon={<AddIcon />} onClick={() => setAppointing(true)}>{t('org.appoint')}</Button>
                  )}
                </Stack>
              }
            />
            <List dense>
              {(bearers ?? []).length === 0 && (
                <Typography color="text.secondary" sx={{ px: 2, pb: 2 }}>{t('org.noBearers')}</Typography>
              )}
              {(bearers ?? []).map((b) => (
                <ListItem
                  key={b.id}
                  secondaryAction={
                    b.current && unit.can_manage ? (
                      <Button size="small" onClick={() => void endTerm(b.id, b.holder_name)}>{t('org.endTerm')}</Button>
                    ) : !b.current ? (
                      <Chip size="small" label={t('users.ended')} />
                    ) : undefined
                  }
                  sx={{ opacity: b.current ? 1 : 0.6 }}
                >
                  <ListItemIcon><BadgeIcon color={b.current ? 'primary' : 'disabled'} /></ListItemIcon>
                  <ListItemText
                    primary={<><strong>{b.position_name}</strong> · {b.holder_name}</>}
                    secondary={[
                      `${formatDate(b.valid_from)} – ${b.valid_to ? formatDate(b.valid_to) : t('org.present')}`,
                      b.grants_role ? t('org.roleGranted', { role: b.grants_role }) : null,
                    ].filter(Boolean).join(' · ')}
                  />
                </ListItem>
              ))}
            </List>
          </Card>
        </Grid>
        <Grid size={12}>
          <Card>
            <CardHeader
              title={t('org.subUnits')}
              action={can('org_unit.create') && unit.status === 'ACTIVE' && (
                <Button startIcon={<AddIcon />} onClick={() => setAddingChild(true)}>{t('org.addSubUnit')}</Button>
              )}
            />
            <List dense>
              {(children ?? []).length === 0 && (
                <Typography color="text.secondary" sx={{ px: 2, pb: 2 }}>{t('common.noRecords')}</Typography>
              )}
              {(children ?? []).map((c) => (
                <ListItemButton key={c.id} onClick={() => navigate(`/org/units/${c.id}`)}>
                  <ListItemText primary={`${c.name} (${c.code})`} secondary={c.type_name} />
                  <StatusBadge status={c.status} />
                </ListItemButton>
              ))}
            </List>
          </Card>
        </Grid>
      </Grid>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        <Link component={RouterLink} to={typePath(unit.type_code)}>← {type?.name_plural ?? unit.type_name}</Link>
      </Typography>
      {type && (
        <>
          <OrgUnitDialog open={editing} onClose={() => setEditing(false)} type={type} unit={unit} />
          <OrgUnitDialog open={addingChild} onClose={() => setAddingChild(false)} type={type}
            defaultParent={{ id: unit.id, name: unit.name, code: unit.code }}
            onSaved={(u) => navigate(`/org/units/${u.id}`)} />
          <AppointDialog open={appointing} onClose={() => setAppointing(false)} unit={unit} positions={type.positions} />
        </>
      )}
    </>
  );
}
