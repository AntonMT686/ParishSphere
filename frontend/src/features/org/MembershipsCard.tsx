import AddIcon from '@mui/icons-material/PersonAddAlt1Outlined';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardHeader from '@mui/material/CardHeader';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Pagination from '@mui/material/Pagination';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api, type Page } from '@/api/client';
import type { FamilyListItem, Member, Membership, OrgUnit, OrgUnitType } from '@/api/types';
import { useFeedback } from '@/design-system';
import { formatDate } from '@/lib/format';
import { FamilyPicker, MemberPicker } from '@/features/people/pickers';

export function MembershipsCard({ unit, type }: { unit: OrgUnit; type: OrgUnitType }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const [page, setPage] = useState(1);
  const [history, setHistory] = useState(false);
  const [adding, setAdding] = useState(false);
  const [member, setMember] = useState<Member | null>(null);
  const [family, setFamily] = useState<FamilyListItem | null>(null);
  const isAnbiyam = type.code === 'ANBIYAM';
  const familyKind = type.member_kind === 'FAMILY';
  const key = ['org', 'units', 'memberships', unit.id, page, history];
  const { data } = useQuery({
    queryKey: key,
    queryFn: async () => (await api.get<Page<Membership>>(`/org-units/${unit.id}/memberships`, { params: { page, size: 20, include_history: history } })).data,
  });
  const refresh = () => qc.invalidateQueries({ queryKey: ['org', 'units', 'memberships', unit.id] });
  const add = useMutation({
    mutationFn: () => api.post(`/org-units/${unit.id}/memberships`, familyKind ? { family_id: family?.id } : { member_id: member?.id }),
    onSuccess: () => { toast(t('common.saved')); setAdding(false); setMember(null); setFamily(null); void refresh(); },
    onError: toastError,
  });
  const end = async (m: Membership) => {
    if (!m.id || !(await confirm({ title: t('org.endMembership'), message: m.member?.name ?? m.family?.name }))) return;
    try {
      await api.post(`/org-units/${unit.id}/memberships/${m.id}/end`, {});
      toast(t('common.saved'));
      void refresh();
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <Card>
      <CardHeader
        title={isAnbiyam ? t('nav.families') : t('nav.members')}
        subheader={data ? t('people.activeCount', { n: data.total }) : undefined}
        action={
          <Stack direction="row" spacing={1} alignItems="center">
            {!isAnbiyam && <FormControlLabel control={<Switch size="small" checked={history} onChange={(_, v) => setHistory(v)} />} label={t('users.history')} />}
            {!isAnbiyam && unit.can_manage && unit.status === 'ACTIVE' && (
              <Button startIcon={<AddIcon />} onClick={() => setAdding(true)}>{t('org.addMember')}</Button>
            )}
          </Stack>
        }
      />
      {isAnbiyam && <Typography variant="body2" color="text.secondary" sx={{ px: 2 }}>{t('org.anbiyamFamiliesHint')}</Typography>}
      <List dense>
        {(data?.items ?? []).length === 0 && <Typography color="text.secondary" sx={{ px: 2, pb: 2 }}>{t('common.noRecords')}</Typography>}
        {(data?.items ?? []).map((m) => (
          <ListItem key={m.id ?? m.family?.id} disablePadding
            secondaryAction={m.current && m.id && unit.can_manage ? <Button size="small" onClick={() => void end(m)}>{t('org.endMembership')}</Button> : undefined}>
            <ListItemButton onClick={() => m.family && navigate(`/families/${m.family.id}`)} sx={{ opacity: m.current ? 1 : 0.6 }}>
              <ListItemText
                primary={m.member ? `${m.member.name} · ${m.member.code}` : `${m.family?.name} · ${m.family?.code}`}
                secondary={[m.member && m.family?.name, m.age !== null && m.age !== undefined ? `${m.age} ${t('people.years')}` : null,
                  m.joined_on && `${t('users.validFrom')} ${formatDate(m.joined_on)}`, m.left_on && `${t('users.validTo')} ${formatDate(m.left_on)}`]
                  .filter(Boolean).join(' · ')}
              />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      {data && data.pages > 1 && <Stack alignItems="center" sx={{ pb: 2 }}><Pagination count={data.pages} page={page} onChange={(_, p) => setPage(p)} /></Stack>}
      <Dialog open={adding} onClose={() => setAdding(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t('org.addMember')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {familyKind ? <FamilyPicker label={t('people.family')} value={family} onChange={setFamily} />
              : <MemberPicker label={t('people.member')} value={member} onChange={setMember} />}
            {Object.keys(type.membership_rules ?? {}).length > 0 && (
              <Typography variant="body2" color="text.secondary">{t('org.rulesApply')}</Typography>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAdding(false)}>{t('common.cancel')}</Button>
          <Button variant="contained" disabled={(familyKind ? !family : !member) || add.isPending} onClick={() => add.mutate()}>{t('org.addMember')}</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
