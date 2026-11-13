import PlayArrowIcon from '@mui/icons-material/PlayArrowOutlined';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router-dom';
import type { ReportData, ReportInfo } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { ExportMenu, PageHeader, StatusBadge } from '@/design-system';
import { inr } from '@/features/finance/api';
import { OrgUnitPicker } from '@/features/org/pickers';
import { formatDate, formatDateTime } from '@/lib/format';
import { NotFoundPage } from '@/features/NotFoundPage';
import { clean, initialParams, type Params, useReport, useReportCatalog } from './api';

type Col = ReportData['columns'][number];

function cell(c: Col, v: unknown) {
  if (v === null || v === undefined || v === '') return '';
  if (c.kind === 'money') return inr(v as string);
  if (c.kind === 'number') return typeof v === 'number' ? v.toLocaleString('en-IN') : String(v);
  if (c.kind === 'date') return String(v).length > 10 ? formatDateTime(String(v).replace(' ', 'T')) : formatDate(String(v));
  if (c.kind === 'status') return /^[A-Z_]+$/.test(String(v)) ? <StatusBadge status={String(v)} /> : String(v);
  return String(v);
}

function fyOptions(): { value: string; label: string }[] {
  const y = new Date().getFullYear();
  return [0, 1, 2, 3, 4].map((i) => ({ value: String(y - i), label: `${y - i}–${String(y - i + 1).slice(2)}` }));
}

function Filters({ r, value, onChange }: { r: ReportInfo; value: Params; onChange: (p: Params) => void }) {
  const { t } = useTranslation();
  const can = useCan();
  const [unit, setUnit] = useState<{ id: string; name: string; code: string } | null>(null);
  const set = (k: string, v: string) => onChange({ ...value, [k]: v });
  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} flexWrap="wrap" useFlexGap>
      {r.params.map((p) => {
        switch (p.name) {
          case 'date_range':
            return (
              <Stack key="dr" direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <TextField type="date" label={t('reports.from')} value={value.date_from ?? ''} onChange={(e) => set('date_from', e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
                <TextField type="date" label={t('reports.to')} value={value.date_to ?? ''} onChange={(e) => set('date_to', e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
              </Stack>
            );
          case 'month':
            return <TextField key="m" type="month" label={t('reports.month')} value={value.month ?? ''} onChange={(e) => set('month', e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />;
          case 'fy':
            return (
              <TextField key="fy" select label={t('reports.fy')} value={value.fy ?? ''} onChange={(e) => set('fy', e.target.value)} sx={{ minWidth: { md: 160 } }}>
                <MenuItem value="">{t('reports.current')}</MenuItem>
                {fyOptions().map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </TextField>
            );
          case 'org_unit':
            return can('org_unit.view') ? (
              <Box key="ou" sx={{ minWidth: { md: 260 } }}>
                <OrgUnitPicker label={t('reports.organisation')} value={unit} onChange={(u) => { setUnit(u); set('org_unit', u?.id ?? ''); }} />
              </Box>
            ) : null;
          default:
            return (
              <TextField key={p.name} select label={t(`reports.param.${p.name}`)} value={value[p.name] ?? ''} onChange={(e) => set(p.name, e.target.value)} sx={{ minWidth: { md: 180 } }}>
                {!p.default && <MenuItem value="">{t('reports.all')}</MenuItem>}
                {p.options.map((o) => <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>)}
              </TextField>
            );
        }
      })}
    </Stack>
  );
}

export function ReportPage() {
  const { t } = useTranslation();
  const { code = '' } = useParams();
  const { data: catalog, isLoading } = useReportCatalog();
  const info = catalog?.find((r) => r.code === code);
  const [draft, setDraft] = useState<Params>({});
  const [applied, setApplied] = useState<Params | null>(null);
  useEffect(() => {
    if (info) { const p = initialParams(info); setDraft(p); setApplied(p); }
  }, [info]);
  const { data, isFetching, error } = useReport(code, applied);
  if (isLoading) return <LinearProgress />;
  if (!info) return <NotFoundPage />;
  const title = t(`reports.r.${info.code}.title`, info.title);
  const short = new Set(
    (data?.columns ?? []).filter((c) => c.kind !== 'text' || data!.rows.every((r) => String(r[c.key] ?? '').length <= 24)).map((c) => c.key),
  );
  return (
    <>
      <PageHeader title={title} subtitle={data?.subtitle ?? t(`reports.r.${info.code}.desc`, info.description)}
        breadcrumbs={[{ label: t('reports.title'), to: '/reports' }, { label: title }]}
        actions={info.can_export && applied ? <ExportMenu url={`/reports/${code}/export`} params={applied} filename={code.replace(/_/g, '-')} /> : undefined} />
      {info.params.length > 0 && (
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1.5} alignItems={{ lg: 'center' }}>
              <Filters r={info} value={draft} onChange={setDraft} />
              <Box sx={{ flexGrow: 1 }} />
              <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={() => setApplied(clean(draft))}>{t('reports.run')}</Button>
            </Stack>
          </CardContent>
        </Card>
      )}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{(error as { message?: string }).message ?? t('errors.generic')}</Alert>}
      <Card>
        {isFetching && <LinearProgress />}
        {data && (
          <>
            {data.truncated && <Alert severity="info" sx={{ m: 2 }}>{t('reports.truncated', { shown: data.rows.length, total: data.total_rows })}</Alert>}
            {data.rows.length === 0 ? (
              <Typography color="text.secondary" sx={{ p: 3 }}>{t('reports.empty')}</Typography>
            ) : (
              <TableContainer sx={{ maxHeight: '70vh' }}>
                <Table size="small" stickyHeader aria-label={title}>
                  <TableHead>
                    <TableRow>
                      {data.columns.map((c) => (
                        <TableCell key={c.key} align={c.kind === 'money' || c.kind === 'number' ? 'right' : 'left'} sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}>{c.header}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.rows.map((row, i) => (
                      <TableRow key={i} hover>
                        {data.columns.map((c) => (
                          <TableCell key={c.key} align={c.kind === 'money' || c.kind === 'number' ? 'right' : 'left'}
                            sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: short.has(c.key) ? 'nowrap' : undefined, minWidth: short.has(c.key) ? undefined : 160 }}>{cell(c, row[c.key])}</TableCell>
                        ))}
                      </TableRow>
                    ))}
                    {data.totals && (
                      <TableRow sx={{ '& td': { fontWeight: 700, borderTop: 2, borderColor: 'divider' } }}>
                        {data.columns.map((c) => (
                          <TableCell key={c.key} align={c.kind === 'money' || c.kind === 'number' ? 'right' : 'left'} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                            {data.totals?.[c.key] !== undefined ? cell(c.kind === 'status' ? { ...c, kind: 'text' } : c, data.totals[c.key]) : ''}
                          </TableCell>
                        ))}
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </>
        )}
      </Card>
    </>
  );
}
