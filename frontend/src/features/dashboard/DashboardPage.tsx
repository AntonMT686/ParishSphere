import FactCheckIcon from '@mui/icons-material/FactCheckOutlined';
import FamilyIcon from '@mui/icons-material/FamilyRestroomOutlined';
import GroupsIcon from '@mui/icons-material/GroupsOutlined';
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined';
import ReceiptIcon from '@mui/icons-material/ReceiptLongOutlined';
import ChurchIcon from '@mui/icons-material/ChurchOutlined';
import VolunteerIcon from '@mui/icons-material/VolunteerActivismOutlined';
import Avatar from '@mui/material/Avatar';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid2';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useTenantBranding } from '@/api/tenant';
import { useCan } from '@/auth/authStore';
import { PageHeader, StatCard } from '@/design-system';
import { useClergy } from '@/features/parish/api';
import { useDashboard } from './api';
import { DashboardAgenda } from './DashboardAgenda';
import { DashboardFinance } from './DashboardFinance';
import { DashboardNotices } from './DashboardNotices';
import {
  ActivitiesSection, AgeChart, AnbiyamChart, ApprovalsCard, CategoryChart, EventsCard, FinanceStatus, IncomeExpenseChart,
  MeSection, OrganisationsCard,
} from './sections';

interface Stat { key: string; label: string; value: ReactNode; icon: ReactNode; tone: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info'; to?: string; hint?: ReactNode }

/**
 * Role-based dashboard. Sections follow the user's permissions (see GET /dashboard): the Parish Priest sees
 * everything, the President/Secretary their review queues and committee activity, the Treasurer the money,
 * an Anbiyam leader their Anbiyam, and a parishioner their family, events and notices.
 */
export function DashboardPage() {
  const { t } = useTranslation();
  const can = useCan();
  const navigate = useNavigate();
  const { data: branding } = useTenantBranding();
  const { data: clergy } = useClergy();
  const { data: d, isLoading } = useDashboard();
  const parish = branding?.display_name ?? t('app.name');
  const staff = Boolean(d && (d.people || d.finance || d.activities || d.organisations || d.approvals.pending));
  const unitStat = (code: string) => d?.organisations?.find((o) => o.code === code);

  const stats: Stat[] = [];
  if (d?.people) {
    stats.push({ key: 'families', label: t('dashboard.families'), value: d.people.families.toLocaleString('en-IN'), icon: <FamilyIcon />, tone: 'primary', to: '/families',
      hint: d.people.new_families_month ? t('dashboard.newThisMonth', { count: d.people.new_families_month }) : undefined });
    stats.push({ key: 'members', label: t('dashboard.members'), value: d.people.members.toLocaleString('en-IN'), icon: <PeopleIcon />, tone: 'info', to: can('member.view') ? '/members' : undefined });
  }
  for (const [code, key, tone] of [['ANBIYAM', 'anbiyam', 'secondary'], ['SOCIETY', 'societies', 'success']] as const) {
    const u = unitStat(code);
    if (u) stats.push({ key, label: u.name, value: u.units, icon: <GroupsIcon />, tone, to: `/org/${code.toLowerCase()}`,
      hint: t(u.member_kind === 'FAMILY' ? 'dashboard.familiesCount' : 'dashboard.membersCount', { count: u.members }) });
  }
  if (d && staff) {
    stats.push({ key: 'pendingApprovals', label: t('dashboard.pendingApprovals'), value: d.approvals.pending, icon: <FactCheckIcon />, tone: 'warning', to: '/approvals',
      hint: d.approvals.overdue ? t('dashboard.overdueCount', { count: d.approvals.overdue }) : undefined });
  }
  if (d?.finance) {
    stats.push({ key: 'pendingFinance', label: t('dashboard.pendingFinance'), value: d.finance.pending_entries, icon: <ReceiptIcon />, tone: 'error',
      to: can(['finance.view', 'finance.create']) ? '/finance/transactions' : undefined,
      hint: d.approvals.finance ? t('dashboard.withYou', { count: d.approvals.finance }) : undefined });
    if (!d.people) stats.push({ key: 'donations', label: t('dashboard.donationsMonth'), value: Number(d.finance.donations_month).toLocaleString('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }), icon: <VolunteerIcon />, tone: 'success' });
  }

  return (
    <>
      <PageHeader title={t('dashboard.greeting', { parish })} subtitle={branding?.diocese_name} />
      <Grid container spacing={2}>
        {clergy && (clergy.parish_priest || clergy.others.length > 0) && (
          <Grid size={12}>
            <Card>
              <CardContent>
                <Stack direction={{ xs: 'column', md: 'row' }} spacing={{ xs: 1.5, md: 4 }} alignItems={{ md: 'center' }}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Avatar sx={{ bgcolor: 'primary.main' }}><ChurchIcon /></Avatar>
                    <div>
                      <Typography variant="caption" color="text.secondary">{t('priests.role.PARISH_PRIEST')}</Typography>
                      <Typography variant="subtitle1" fontWeight={600}>{clergy.parish_priest?.name ?? '—'}</Typography>
                    </div>
                  </Stack>
                  {clergy.others.map((o) => (
                    <div key={`${o.id}-${o.role}`}>
                      <Typography variant="caption" color="text.secondary">{t(`priests.role.${o.role}`)}</Typography>
                      <Typography variant="body2">{o.name}</Typography>
                    </div>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        )}
        {isLoading && [0, 1, 2, 3].map((i) => (
          <Grid key={i} size={{ xs: 12, sm: 6, lg: 3 }}><StatCard label="" value="" loading /></Grid>
        ))}
        {stats.map((s) => (
          <Grid key={s.key} size={{ xs: 12, sm: 6, lg: 4, xl: 12 / Math.min(stats.length, 6) }}>
            <StatCard label={s.label} value={s.value} icon={s.icon} tone={s.tone} hint={s.hint} onClick={s.to ? () => navigate(s.to!) : undefined} />
          </Grid>
        ))}

        {d?.me && <MeSection me={d.me} />}
        <DashboardNotices />

        {d?.finance ? (
          <>
            <Grid size={{ xs: 12, lg: 8 }}><IncomeExpenseChart f={d.finance} /></Grid>
            <Grid size={{ xs: 12, lg: 4 }}><ApprovalsCard a={d.approvals} /></Grid>
          </>
        ) : d && staff && (
          <Grid size={{ xs: 12, md: 6 }}><ApprovalsCard a={d.approvals} /></Grid>
        )}
        {d && (staff || d.events.length > 0) && (
          <Grid size={{ xs: 12, md: d.finance || !staff ? 12 : 6, lg: d.finance ? 4 : undefined }}>
            <EventsCard events={d.events} linked={can(['activity.view', 'meeting.view'])} />
          </Grid>
        )}
        {d?.finance && (
          <>
            <Grid size={{ xs: 12, md: 6, lg: 4 }}><CategoryChart f={d.finance} kind="INCOME" /></Grid>
            <Grid size={{ xs: 12, md: 6, lg: 4 }}><CategoryChart f={d.finance} kind="EXPENSE" /></Grid>
            <DashboardFinance />
            <Grid size={12}><FinanceStatus f={d.finance} /></Grid>
          </>
        )}

        {d?.people && (
          <>
            <Grid size={{ xs: 12, md: 6 }}><AnbiyamChart p={d.people} /></Grid>
            <Grid size={{ xs: 12, md: 6 }}><AgeChart p={d.people} /></Grid>
          </>
        )}
        {d?.organisations && d.organisations.length > 0 && <Grid size={12}><OrganisationsCard orgs={d.organisations} /></Grid>}
        {d?.activities && <ActivitiesSection a={d.activities} m={d.meetings ?? null} />}
        <DashboardAgenda />
      </Grid>
    </>
  );
}
