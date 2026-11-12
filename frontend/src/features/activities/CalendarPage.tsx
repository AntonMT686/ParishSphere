import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { CalendarEvent } from '@/api/types';
import { PageHeader, StatusBadge } from '@/design-system';
import { formatWallTime } from '@/lib/format';
import { useCalendar } from './api';
import { OrgUnitSelect } from './shared';

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

function monthGrid(year: number, month: number): Date[] {
  const first = new Date(year, month, 1);
  const start = new Date(first);
  start.setDate(1 - ((first.getDay() + 6) % 7)); // weeks start on Monday
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

function eventDays(e: CalendarEvent): string[] {
  const start = e.start.slice(0, 10);
  if (!e.all_day || !e.end) return [start];
  const out: string[] = [];
  for (let d = new Date(`${start}T00:00`); iso(d) <= e.end.slice(0, 10) && out.length < 31; d.setDate(d.getDate() + 1)) out.push(iso(d));
  return out;
}

function EventChip({ e }: { e: CalendarEvent }) {
  const theme = useTheme();
  const color = e.kind === 'MEETING' ? theme.palette.secondary.main : theme.palette.primary.main;
  return (
    <Box component={RouterLink} to={e.link} title={`${e.title}${e.org_unit ? ` · ${e.org_unit.name}` : ''}`}
      sx={{ display: 'block', textDecoration: 'none', color: 'text.primary', fontSize: 12, lineHeight: 1.35, px: 0.75, py: 0.25, mb: 0.5,
        borderRadius: 1, bgcolor: alpha(color, 0.12), borderLeft: `3px solid ${color}`, overflow: 'hidden', whiteSpace: 'nowrap',
        textOverflow: 'ellipsis', opacity: e.status === 'CANCELLED' ? 0.5 : 1, textDecorationLine: e.status === 'CANCELLED' ? 'line-through' : 'none' }}>
      {!e.all_day && <strong>{formatWallTime(e.start, false)} </strong>}{e.title}
    </Box>
  );
}

export function CalendarPage() {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('md'));
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() });
  const [unit, setUnit] = useState('ALL');
  const days = useMemo(() => monthGrid(ym.y, ym.m), [ym]);
  const { data = [] } = useCalendar(iso(days[0]!), iso(days[41]!), unit === 'ALL' ? undefined : unit === '' ? 'PARISH' : unit);
  const byDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    data.forEach((e) => eventDays(e).forEach((d) => map.set(d, [...(map.get(d) ?? []), e])));
    return map;
  }, [data]);
  const lang = i18n.language === 'ta' ? 'ta-IN' : 'en-IN';
  const title = new Date(ym.y, ym.m, 1).toLocaleString(lang, { month: 'long', year: 'numeric' });
  const shift = (d: number) => setYm(({ y, m }) => ({ y: m + d < 0 ? y - 1 : m + d > 11 ? y + 1 : y, m: (m + d + 12) % 12 }));
  const weekdays = Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleString(lang, { weekday: 'short' }));
  const todayIso = iso(now);
  const monthEvents = data.filter((e) => e.start.slice(0, 7) === `${ym.y}-${String(ym.m + 1).padStart(2, '0')}`);
  return (
    <>
      <PageHeader title={t('nav.calendar')} subtitle={t('calendar.subtitle')} breadcrumbs={[{ label: t('nav.overview') }, { label: t('nav.calendar') }]} />
      <Card sx={{ p: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} sx={{ mb: 2 }}>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <IconButton aria-label={t('calendar.previous')} onClick={() => shift(-1)}><ChevronLeftIcon /></IconButton>
            <Typography variant="h3" sx={{ minWidth: 180, textAlign: 'center' }} aria-live="polite">{title}</Typography>
            <IconButton aria-label={t('calendar.next')} onClick={() => shift(1)}><ChevronRightIcon /></IconButton>
            <Button size="small" onClick={() => setYm({ y: now.getFullYear(), m: now.getMonth() })}>{t('calendar.today')}</Button>
          </Stack>
          <Box sx={{ flexGrow: 1 }} />
          <Stack direction="row" spacing={2} alignItems="center">
            <Stack direction="row" spacing={0.75} alignItems="center"><Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: 'primary.main' }} /><Typography variant="caption">{t('nav.activityList')}</Typography></Stack>
            <Stack direction="row" spacing={0.75} alignItems="center"><Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: 'secondary.main' }} /><Typography variant="caption">{t('nav.meetings')}</Typography></Stack>
          </Stack>
          <OrgUnitSelect permission="activity.view" allowAll value={unit} onChange={setUnit} sx={{ maxWidth: { md: 260 } }} />
        </Stack>
        {compact ? (
          <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={title}>
            {monthEvents.length === 0 && <Typography variant="body2" color="text.secondary">{t('calendar.nothing')}</Typography>}
            {monthEvents.map((e) => (
              <Stack key={`${e.kind}-${e.id}`} component="li" direction="row" spacing={1.5} alignItems="center">
                <Box sx={{ width: 64, flexShrink: 0 }}>
                  <Typography variant="caption" color="text.secondary">{new Date(e.start.replace(/Z$/, '')).toLocaleDateString(lang, { day: 'numeric', month: 'short' })}</Typography>
                </Box>
                <Box sx={{ flexGrow: 1, minWidth: 0 }}><EventChip e={e} /></Box>
                <StatusBadge status={e.status} />
              </Stack>
            ))}
          </Stack>
        ) : (
          <Box role="grid" aria-label={title} sx={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', borderTop: 1, borderLeft: 1, borderColor: 'divider' }}>
            {weekdays.map((w) => (
              <Box key={w} role="columnheader" sx={{ p: 0.75, fontSize: 12, fontWeight: 600, color: 'text.secondary', borderRight: 1, borderBottom: 1, borderColor: 'divider', bgcolor: 'action.hover' }}>{w}</Box>
            ))}
            {days.map((d) => {
              const key = iso(d);
              const events = byDay.get(key) ?? [];
              const other = d.getMonth() !== ym.m;
              return (
                <Box key={key} role="gridcell" aria-label={d.toLocaleDateString(lang, { day: 'numeric', month: 'long' })}
                  sx={{ minHeight: 104, p: 0.75, borderRight: 1, borderBottom: 1, borderColor: 'divider', bgcolor: other ? 'action.hover' : 'background.paper', minWidth: 0 }}>
                  <Typography variant="caption" sx={{ display: 'inline-block', mb: 0.5, px: 0.75, borderRadius: 1, fontWeight: key === todayIso ? 700 : 400,
                    color: key === todayIso ? 'primary.contrastText' : other ? 'text.disabled' : 'text.secondary', bgcolor: key === todayIso ? 'primary.main' : 'transparent' }}>
                    {d.getDate()}
                  </Typography>
                  {events.slice(0, 3).map((e) => <EventChip key={`${e.kind}-${e.id}`} e={e} />)}
                  {events.length > 3 && <Typography variant="caption" color="text.secondary">{t('calendar.more', { count: events.length - 3 })}</Typography>}
                </Box>
              );
            })}
          </Box>
        )}
      </Card>
    </>
  );
}
