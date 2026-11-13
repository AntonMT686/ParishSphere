import AssignmentLateIcon from '@mui/icons-material/AssignmentLateOutlined';
import EventIcon from '@mui/icons-material/EventOutlined';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { Dashboard } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { StatusBadge } from '@/design-system';
import { inr } from '@/features/finance/api';
import { formatDate, formatDateTime } from '@/lib/format';
import { monthLabel } from './api';
import { shortInr, useSeries } from './chartStyle';
import { ChartCard, Empty, HBars, VBars } from './charts';

type D = Dashboard;
const listSx = { listStyle: 'none', p: 0, m: 0 } as const;
const linkSx = { color: 'text.primary', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } } as const;

function ViewAll({ to }: { to: string }) {
  const { t } = useTranslation();
  return <Button size="small" component={RouterLink} to={to}>{t('dashboard.viewAll')}</Button>;
}

/** The user's own approval queue, oldest deadline first. */
export function ApprovalsCard({ a }: { a: D['approvals'] }) {
  const { t } = useTranslation();
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={t('dashboard.myApprovals')} titleTypographyProps={{ variant: 'h6' }}
        subheader={a.pending ? t('dashboard.waitingOverdue', { count: a.pending, overdue: a.overdue }) : undefined}
        action={<ViewAll to="/approvals" />} />
      <CardContent sx={{ pt: 0 }}>
        {a.items.length === 0 && <Typography variant="body2" color="text.secondary">{t('dashboard.nothingWaiting')}</Typography>}
        <Stack component="ul" spacing={1.25} sx={listSx} aria-label={t('dashboard.myApprovals')}>
          {a.items.map((x, i) => (
            <Stack component="li" key={i} direction="row" spacing={1} alignItems="flex-start">
              <AssignmentLateIcon fontSize="small" color={x.overdue ? 'error' : 'action'} sx={{ mt: 0.25 }} />
              <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                <Typography component={x.link ? RouterLink : 'span'} to={x.link ?? undefined} variant="body2" fontWeight={600} sx={{ ...linkSx, display: 'block' }} noWrap>
                  {x.title}
                </Typography>
                <Typography variant="caption" color={x.overdue ? 'error' : 'text.secondary'} component="div">
                  {x.entity_label}{x.stage ? ` · ${x.stage}` : ''}{x.amount != null ? ` · ${inr(x.amount)}` : ''}
                  {x.due_at ? ` · ${t(x.overdue ? 'dashboard.overdueSince' : 'dashboard.dueBy', { date: formatDateTime(x.due_at) })}` : ''}
                </Typography>
              </Box>
            </Stack>
          ))}
        </Stack>
        {a.by_type.length > 1 && (
          <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
            {a.by_type.map((b) => <Chip key={b.key} size="small" variant="outlined" label={`${b.label} · ${b.value}`} />)}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

export function IncomeExpenseChart({ f }: { f: NonNullable<D['finance']> }) {
  const { t } = useTranslation();
  const can = useCan();
  const rows = f.months.map((m) => ({ label: monthLabel(m.key, true), income: Number(m.income), expense: Number(m.expense) }));
  return (
    <ChartCard title={t('dashboard.incomeVsExpense')} subheader={t('dashboard.last12')} rows={rows} height={280}
      columns={[{ key: 'income', label: t('finance.kind.INCOME'), format: inr }, { key: 'expense', label: t('finance.kind.EXPENSE'), format: inr }]}
      action={can(['finance.view', 'finance.create']) ? <ViewAll to="/finance/transactions" /> : undefined}>
      <VBars rows={rows} format={shortInr} tipFormat={inr} series={[{ key: 'income', label: t('finance.kind.INCOME') }, { key: 'expense', label: t('finance.kind.EXPENSE') }]} />
    </ChartCard>
  );
}

export function CategoryChart({ f, kind }: { f: NonNullable<D['finance']>; kind: 'INCOME' | 'EXPENSE' }) {
  const { t } = useTranslation();
  const colors = useSeries();
  const src = kind === 'INCOME' ? f.income_by_category : f.expense_by_category;
  const rows = src.slice(0, 7).map((c) => ({ label: c.name, amount: Number(c.amount) }));
  return (
    <ChartCard title={t(kind === 'INCOME' ? 'dashboard.incomeByCategory' : 'dashboard.expenseByCategory')} subheader={f.fy_label}
      rows={rows} columns={[{ key: 'amount', label: t('finance.amount'), format: inr }]} height={Math.max(140, rows.length * 34 + 30)}>
      {rows.length ? <HBars rows={rows} valueKey="amount" format={shortInr} tipFormat={inr} color={colors[kind === 'INCOME' ? 0 : 1]!} /> : <Empty text={t('dashboard.noEntries')} />}
    </ChartCard>
  );
}

/** Donations, pending entries and the status of the last six months' statements. */
export function FinanceStatus({ f }: { f: NonNullable<D['finance']> }) {
  const { t } = useTranslation();
  const can = useCan();
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={t('dashboard.donationsAndStatements')} titleTypographyProps={{ variant: 'h6' }}
        action={can('finance_period.view') ? <ViewAll to="/finance/statements" /> : undefined} />
      <CardContent sx={{ pt: 0 }}>
        <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
          <Figure label={t('dashboard.donationsMonth')} value={inr(f.donations_month)} />
          <Figure label={t('dashboard.donationsFy', { fy: f.fy_label })} value={inr(f.donations_fy)} />
          <Figure label={t('finance.awaitingApproval')} value={String(f.pending_entries)} warn={f.pending_entries > 0} />
        </Stack>
        {f.periods.length > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="caption" color="text.secondary">{t('dashboard.statements')}</Typography>
            <Stack component="ol" direction="row" sx={{ ...listSx, mt: 1 }} spacing={1} flexWrap="wrap" useFlexGap aria-label={t('dashboard.statements')}>
              {f.periods.map((p) => (
                <Stack component="li" key={p.key} spacing={0.5} alignItems="flex-start" sx={{ minWidth: 92 }}>
                  <Typography component={RouterLink} to={`/finance/statements/${p.key}`} variant="body2" fontWeight={600} sx={linkSx}>{monthLabel(p.key)}</Typography>
                  <StatusBadge status={p.status} />
                </Stack>
              ))}
            </Stack>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Figure({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h4" color={warn ? 'warning.main' : undefined} sx={{ fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
    </div>
  );
}

export function AnbiyamChart({ p }: { p: NonNullable<D['people']> }) {
  const { t } = useTranslation();
  const colors = useSeries();
  const rows = p.by_anbiyam.slice(0, 10).map((a) => ({ label: a.name, families: a.families, members: a.members }));
  return (
    <ChartCard title={t('dashboard.familiesByAnbiyam')} rows={rows} action={<ViewAll to="/families" />}
      subheader={p.pending_anbiyam ? t('dashboard.pendingAnbiyam', { count: p.pending_anbiyam }) : undefined}
      columns={[{ key: 'families', label: t('dashboard.families') }, { key: 'members', label: t('dashboard.members') }]}
      height={Math.max(140, rows.length * 34 + 30)}>
      {rows.length ? <HBars rows={rows} valueKey="families" color={colors[0]!} /> : <Empty text={t('dashboard.noFamilies')} />}
    </ChartCard>
  );
}

export function AgeChart({ p }: { p: NonNullable<D['people']> }) {
  const { t } = useTranslation();
  const can = useCan();
  const rows = p.age_bands.map((b) => ({ label: b.label, members: b.value }));
  const gender = p.gender.map((g) => `${t(`people.gender.${g.key}`)} ${g.value}`).join(' · ');
  return (
    <ChartCard title={t('dashboard.membersByAge')} subheader={gender || undefined} rows={rows}
      columns={[{ key: 'members', label: t('dashboard.members') }]} action={can('member.view') ? <ViewAll to="/members" /> : undefined}>
      {p.members ? <VBars rows={rows} series={[{ key: 'members', label: t('dashboard.members') }]} /> : <Empty text={t('dashboard.noFamilies')} />}
    </ChartCard>
  );
}

export function OrganisationsCard({ orgs }: { orgs: NonNullable<D['organisations']> }) {
  const { t } = useTranslation();
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={t('dashboard.organisations')} titleTypographyProps={{ variant: 'h6' }} />
      <CardContent sx={{ pt: 0 }}>
        {orgs.length === 0 && <Typography variant="body2" color="text.secondary">{t('dashboard.noOrganisations')}</Typography>}
        <Stack component="ul" divider={<Divider flexItem />} spacing={1} sx={listSx} aria-label={t('dashboard.organisations')}>
          {orgs.map((o) => (
            <Stack component="li" key={o.code} direction="row" alignItems="center" spacing={2}>
              <Typography component={RouterLink} to={`/org/${o.code.toLowerCase()}`} variant="body2" fontWeight={600} sx={{ ...linkSx, flexGrow: 1 }}>{o.name}</Typography>
              <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>{t('dashboard.unitsCount', { count: o.units })}</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: 96, textAlign: 'right' }}>
                {t(o.member_kind === 'FAMILY' ? 'dashboard.familiesCount' : 'dashboard.membersCount', { count: o.members })}
              </Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

type Item = D['events'][number];
function ActivityList({ items, empty, label }: { items: Item[]; empty: string; label: string }) {
  if (!items.length) return <Typography variant="body2" color="text.secondary">{empty}</Typography>;
  return (
    <Stack component="ul" spacing={1.25} sx={listSx} aria-label={label}>
      {items.map((a) => (
        <Stack component="li" key={a.id} direction="row" spacing={1.5} alignItems="center">
          <Box sx={{ width: 44, textAlign: 'center', flexShrink: 0, borderRadius: 1.5, bgcolor: 'action.hover', py: 0.5 }}>
            <Typography variant="caption" component="div" color="text.secondary" lineHeight={1.2}>
              {new Date(`${a.date}T00:00`).toLocaleDateString('en-IN', { month: 'short' })}
            </Typography>
            <Typography variant="subtitle2" component="div" lineHeight={1.2}>{Number(a.date.slice(8))}</Typography>
          </Box>
          <Box sx={{ minWidth: 0, flexGrow: 1 }}>
            <Typography component={RouterLink} to={`/activities/${a.id}`} variant="body2" fontWeight={600} noWrap sx={{ ...linkSx, display: 'block' }}>{a.title}</Typography>
            <Typography variant="caption" color="text.secondary">{a.org_unit ?? ''}</Typography>
          </Box>
          {a.status === 'IN_REVIEW' && <StatusBadge status={a.status} />}
        </Stack>
      ))}
    </Stack>
  );
}

/** Upcoming parish events — for everyone, including parishioners without access to activities. */
export function EventsCard({ events, linked }: { events: Item[]; linked: boolean }) {
  const { t } = useTranslation();
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader avatar={<EventIcon color="primary" />} title={t('dashboard.upcomingEvents')} titleTypographyProps={{ variant: 'h6' }}
        action={linked ? <ViewAll to="/calendar" /> : undefined} />
      <CardContent sx={{ pt: 0 }}>
        {events.length ? (
          <Stack component="ul" spacing={1.25} sx={listSx} aria-label={t('dashboard.upcomingEvents')}>
            {events.map((a) => (
              <Stack component="li" key={a.id} direction="row" spacing={1.5} alignItems="center">
                <Typography variant="body2" color="text.secondary" sx={{ minWidth: 92 }}>{formatDate(a.date)}</Typography>
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={600} noWrap>{a.title}</Typography>
                  {a.org_unit && <Typography variant="caption" color="text.secondary">{a.org_unit}</Typography>}
                </Box>
              </Stack>
            ))}
          </Stack>
        ) : <Typography variant="body2" color="text.secondary">{t('dashboard.noEvents')}</Typography>}
      </CardContent>
    </Card>
  );
}

/** President / Secretary view: review queues, upcoming and recent activities, committee summary. */
export function ActivitiesSection({ a, m }: { a: NonNullable<D['activities']>; m: D['meetings'] }) {
  const { t } = useTranslation();
  const rows = a.by_unit.map((u) => ({ label: u.name || t('activities.parishLevel'), completed: u.completed, planned: u.planned }));
  const counters = [
    { label: t('dashboard.activitiesInReview'), value: a.in_review, to: '/activities' },
    { label: t('dashboard.awaitingReport'), value: a.awaiting_report, to: '/activities' },
    ...(m ? [
      { label: t('dashboard.minutesInReview'), value: m.minutes_in_review, to: '/meetings' },
      { label: t('dashboard.upcomingMeetings'), value: m.upcoming, to: '/meetings' },
    ] : []),
  ];
  return (
    <>
      <Grid size={12}>
        <Grid container spacing={2}>
          {counters.map((c) => (
            <Grid key={c.label} size={{ xs: 6, md: 3 }}>
              <Card component={RouterLink} to={c.to} sx={{ display: 'block', textDecoration: 'none', height: '100%', '&:hover': { borderColor: 'primary.main' } }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                  <Typography variant="h4" color={c.value ? 'text.primary' : 'text.secondary'} sx={{ fontVariantNumeric: 'tabular-nums' }}>{c.value}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Card sx={{ height: '100%' }}>
          <CardHeader title={t('dashboard.upcomingActivities')} titleTypographyProps={{ variant: 'h6' }} action={<ViewAll to="/activities" />} />
          <CardContent sx={{ pt: 0 }}>
            <ActivityList items={a.upcoming} empty={t('dashboard.noUpcomingActivities')} label={t('dashboard.upcomingActivities')} />
          </CardContent>
        </Card>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Card sx={{ height: '100%' }}>
          <CardHeader title={t('dashboard.recentActivities')} titleTypographyProps={{ variant: 'h6' }} />
          <CardContent sx={{ pt: 0 }}>
            <ActivityList items={a.recent} empty={t('dashboard.noRecentActivities')} label={t('dashboard.recentActivities')} />
          </CardContent>
        </Card>
      </Grid>
      {rows.length > 0 && (
        <Grid size={12}>
          <ChartCard title={t('dashboard.activityByOrganisation')} subheader={t('dashboard.last12')} rows={rows}
            columns={[{ key: 'completed', label: t('status.COMPLETED') }, { key: 'planned', label: t('dashboard.planned') }]}>
            <VBars rows={rows} stacked series={[{ key: 'completed', label: t('status.COMPLETED') }, { key: 'planned', label: t('dashboard.planned') }]} />
          </ChartCard>
        </Grid>
      )}
    </>
  );
}

/** Parishioner view: me, my family, my Anbiyam and organisations, my family's donations. */
export function MeSection({ me }: { me: NonNullable<D['me']> }) {
  const { t } = useTranslation();
  return (
    <>
      <Grid size={{ xs: 12, md: 6 }}>
        <Card sx={{ height: '100%' }}>
          <CardHeader title={t('dashboard.myFamily')} titleTypographyProps={{ variant: 'h6' }}
            subheader={[me.family?.name, me.family_code].filter(Boolean).join(' · ')} />
          <CardContent sx={{ pt: 0 }}>
            <Stack direction="row" spacing={4} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
              <div>
                <Typography variant="caption" color="text.secondary">{t('dashboard.me')}</Typography>
                <Typography variant="body2" fontWeight={600}>{me.name} · {me.member_code}</Typography>
              </div>
              <div>
                <Typography variant="caption" color="text.secondary">{t('dashboard.anbiyam')}</Typography>
                <Typography variant="body2" fontWeight={600}>{me.anbiyam ?? '—'}</Typography>
              </div>
            </Stack>
            <Stack component="ul" spacing={0.75} sx={listSx} aria-label={t('dashboard.household')}>
              {me.household.map((h, i) => (
                <Stack component="li" key={i} direction="row" justifyContent="space-between">
                  <Typography variant="body2">{h.name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {t(`people.rel.${h.relationship}`)}{h.age != null ? ` · ${t('dashboard.age', { age: h.age })}` : ''}
                  </Typography>
                </Stack>
              ))}
            </Stack>
            {me.memberships.length > 0 && (
              <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
                {me.memberships.map((n) => <Chip key={n} size="small" label={n} />)}
              </Stack>
            )}
          </CardContent>
        </Card>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Card sx={{ height: '100%' }}>
          <CardHeader title={t('dashboard.myDonations')} titleTypographyProps={{ variant: 'h6' }}
            subheader={t('dashboard.donatedThisFy', { amount: inr(me.donations_fy) })} />
          <CardContent sx={{ pt: 0 }}>
            {me.donations.length === 0 && <Typography variant="body2" color="text.secondary">{t('dashboard.noDonations')}</Typography>}
            <Stack component="ul" spacing={0.75} sx={listSx} aria-label={t('dashboard.myDonations')}>
              {me.donations.map((d) => (
                <Stack component="li" key={d.code} direction="row" spacing={2} alignItems="baseline">
                  <Typography variant="body2" color="text.secondary" sx={{ minWidth: 92 }}>{formatDate(d.date)}</Typography>
                  <Typography variant="body2" sx={{ flexGrow: 1 }} noWrap>{d.category ?? '—'}</Typography>
                  <Typography variant="body2" fontWeight={600} sx={{ fontVariantNumeric: 'tabular-nums' }}>{inr(d.amount)}</Typography>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </>
  );
}
