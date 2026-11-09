import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { GridColDef } from '@mui/x-data-grid';
import { useDeferredValue, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type Page } from '@/api/client';
import type { AuditLog } from '@/api/types';
import { PermissionGate } from '@/auth/guards';
import { DataTable, ExportMenu, PageHeader } from '@/design-system';
import { formatDateTime } from '@/lib/format';

function show(v: unknown): string {
  if (v === null || v === undefined) return '—';
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}

function ChangesDialog({ log, onClose }: { log: AuditLog | null; onClose: () => void }) {
  const { t } = useTranslation();
  const keys = [...new Set([...Object.keys(log?.old_values ?? {}), ...Object.keys(log?.new_values ?? {})])];
  return (
    <Dialog open={Boolean(log)} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {log?.action} · {log?.module}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {log && formatDateTime(log.occurred_at)} · {log?.username ?? '—'} · {log?.ip ?? ''}
        </Typography>
        {log?.remarks && <Typography gutterBottom>{log.remarks}</Typography>}
        {keys.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell />
                <TableCell>{t('audit.old')}</TableCell>
                <TableCell>{t('audit.new')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k}>
                  <TableCell sx={{ fontWeight: 600 }}>{k}</TableCell>
                  <TableCell sx={{ wordBreak: 'break-word' }}>{show(log?.old_values?.[k])}</TableCell>
                  <TableCell sx={{ wordBreak: 'break-word' }}>{show(log?.new_values?.[k])}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function AuditLogPage() {
  const { t } = useTranslation();
  const [filters, setFilters] = useState({ q: '', action: '', module: '', date_from: '', date_to: '' });
  const deferred = useDeferredValue(filters);
  const [open, setOpen] = useState<AuditLog | null>(null);
  const params = Object.fromEntries(Object.entries(deferred).filter(([, v]) => v));
  const set = (k: keyof typeof filters) => (e: React.ChangeEvent<HTMLInputElement>) => setFilters({ ...filters, [k]: e.target.value });

  const columns: GridColDef<AuditLog>[] = [
    { field: 'occurred_at', headerName: t('audit.when'), width: 180, valueFormatter: (v: string) => formatDateTime(v) },
    { field: 'username', headerName: t('audit.user'), width: 140, sortable: false, valueFormatter: (v: string | null) => v ?? '—' },
    { field: 'action', headerName: t('audit.action'), width: 170 },
    { field: 'module', headerName: t('audit.module'), width: 120 },
    { field: 'entity_type', headerName: t('audit.record'), width: 120, sortable: false },
    { field: 'remarks', headerName: t('audit.remarks'), flex: 1, minWidth: 200, sortable: false },
    {
      field: 'changes',
      headerName: t('audit.changes'),
      width: 120,
      sortable: false,
      renderCell: ({ row }) =>
        row.old_values || row.new_values ? (
          <Button size="small" onClick={(e) => { e.stopPropagation(); setOpen(row); }}>
            {t('audit.changes')}
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        title={t('audit.title')}
        subtitle={t('audit.subtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('audit.title') }]}
        actions={
          <PermissionGate anyOf="audit.export">
            <ExportMenu url="/audit-logs/export" params={params} filename="audit-log" />
          </PermissionGate>
        }
      />
      <DataTable<AuditLog>
        queryKey={['audit', params]}
        fetchPage={async (req) => (await api.get<Page<AuditLog>>('/audit-logs', { params: { ...req, ...params } })).data}
        columns={columns}
        onRowClick={setOpen}
        initialSort={[{ field: 'occurred_at', sort: 'desc' }]}
        toolbar={
          <Box>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5}>
              <TextField label={t('common.search')} value={filters.q} onChange={set('q')} />
              <TextField label={t('audit.action')} value={filters.action} onChange={set('action')} placeholder="LOGIN_FAILED" />
              <TextField label={t('audit.module')} value={filters.module} onChange={set('module')} placeholder="auth" />
              <TextField label={t('audit.dateFrom')} type="date" value={filters.date_from} onChange={set('date_from')} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField label={t('audit.dateTo')} type="date" value={filters.date_to} onChange={set('date_to')} slotProps={{ inputLabel: { shrink: true } }} />
            </Stack>
          </Box>
        }
      />
      <ChangesDialog log={open} onClose={() => setOpen(null)} />
    </>
  );
}
