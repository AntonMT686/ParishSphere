import AttachFileIcon from '@mui/icons-material/AttachFile';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import UploadIcon from '@mui/icons-material/UploadFileOutlined';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField, { type TextFieldProps } from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/api/client';
import { StatusBadge, useFeedback } from '@/design-system';
import { ApprovalTimeline } from '@/features/workflow/ApprovalTimeline';
import { DecisionPanel } from '@/features/workflow/ApprovalDetailPage';
import { useEntityApprovals } from '@/features/workflow/api';
import { formatDateTime } from '@/lib/format';
import { actKeys, useAttachments, useMyUnits } from './api';

export const PARISH = '';

/** Organisation selector limited to where the user may act with `permission`. '' = parish level. */
export function OrgUnitSelect({ permission, value, onChange, disabled, current, allowAll, autoSelect, ...rest }: {
  permission: string; value: string; onChange: (id: string) => void; disabled?: boolean;
  current?: { id: string; name: string } | null; allowAll?: boolean;
  /** Pick the first allowed organisation when parish level is not allowed. */
  autoSelect?: boolean;
} & Omit<TextFieldProps, 'value' | 'onChange'>) {
  const { t } = useTranslation();
  const { data } = useMyUnits(permission);
  const units = data?.units ?? [];
  useEffect(() => {
    if (autoSelect && data && !data.parish && value === PARISH && data.units[0]) onChange(data.units[0].id);
  }, [autoSelect, data, value, onChange]);
  const extra = current && !units.some((u) => u.id === current.id) ? [current] : [];
  return (
    <TextField select label={t('activities.organisation')} value={data || value === 'ALL' ? value : ''} disabled={disabled || !data}
      onChange={(e) => onChange(e.target.value)} {...rest}>
      {allowAll && <MenuItem value="ALL">{t('common.all')}</MenuItem>}
      {(data?.parish || value === PARISH) && <MenuItem value={PARISH}>{t('activities.parishLevel')}</MenuItem>}
      {extra.map((u) => <MenuItem key={u.id} value={u.id}>{u.name}</MenuItem>)}
      {units.map((u) => <MenuItem key={u.id} value={u.id}>{u.name} · {u.type_name}</MenuItem>)}
    </TextField>
  );
}

export function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="body2" component="div" sx={{ whiteSpace: 'pre-line' }}>{children || '—'}</Typography>
    </div>
  );
}

const sizeText = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** Files attached to a record. `base` is the record's API path, e.g. `/activities/{id}`. */
export function AttachmentsCard({ base, canAdd, canRemove }: { base: string; canAdd: boolean; canRemove: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const input = useRef<HTMLInputElement>(null);
  const { data = [] } = useAttachments(base);
  const refresh = () => void qc.invalidateQueries({ queryKey: [...actKeys.files, base] });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return api.post(`${base}/attachments`, fd);
    },
    onSuccess: () => { refresh(); toast(t('activities.fileAdded')); },
    onError: toastError,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`${base}/attachments/${id}`),
    onSuccess: () => { refresh(); toast(t('activities.fileRemoved')); },
    onError: toastError,
  });
  return (
    <Card>
      <CardHeader title={t('activities.files')}
        action={canAdd && (
          <>
            <input ref={input} type="file" hidden aria-label={t('activities.addFile')} accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.doc,.xls"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ''; }} />
            <Button size="small" startIcon={<UploadIcon />} disabled={upload.isPending} onClick={() => input.current?.click()}>{t('activities.addFile')}</Button>
          </>
        )} />
      <CardContent sx={{ pt: 0 }}>
        {data.length === 0 && <Typography variant="body2" color="text.secondary">{t('activities.noFiles')}</Typography>}
        <Stack spacing={1}>
          {data.map((f) => (
            <Stack key={f.id} direction="row" spacing={1} alignItems="center">
              <AttachFileIcon fontSize="small" color="action" />
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Link href={f.url} target="_blank" rel="noopener" noWrap sx={{ display: 'block' }}>{f.filename}</Link>
                <Typography variant="caption" color="text.secondary">{sizeText(f.size)} · {f.uploaded_by ?? '—'} · {formatDateTime(f.uploaded_at)}</Typography>
              </Box>
              {canRemove && (
                <Tooltip title={t('common.remove')}>
                  <IconButton aria-label={`${t('common.remove')} ${f.filename}`} onClick={async () => {
                    if (await confirm({ title: t('activities.removeFile', { name: f.filename }), destructive: true })) remove.mutate(f.id);
                  }}><DeleteIcon /></IconButton>
                </Tooltip>
              )}
            </Stack>
          ))}
        </Stack>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1.5 }}>{t('activities.fileHint')}</Typography>
      </CardContent>
    </Card>
  );
}

/** Approval of a record: the decision panel for the current reviewer, and the timeline of the latest run. */
export function ApprovalSection({ entityType, entityId, onChange }: { entityType: string; entityId: string; onChange: () => void }) {
  const { t } = useTranslation();
  const { data = [] } = useEntityApprovals(entityType, entityId);
  const inst = data[0];
  if (!inst) return null;
  const canDecide = inst.status === 'IN_PROGRESS' && (Boolean(inst.my_task) || inst.can_override);
  return (
    <>
      {canDecide && <DecisionPanel key={`${inst.id}-${inst.my_task ?? 'o'}`} instance={inst} onDecided={onChange} />}
      <Card>
        <CardHeader title={t('workflow.timeline')}
          action={<Stack direction="row" spacing={1} alignItems="center">
            <StatusBadge status={inst.status} />
            <Button size="small" component={RouterLink} to={`/approvals/${inst.id}`}>{t('activities.openApproval')}</Button>
          </Stack>}
          subheader={data.length > 1 ? t('activities.approvalRuns', { count: data.length }) : undefined} />
        <CardContent sx={{ pt: 0 }}><ApprovalTimeline instance={inst} /></CardContent>
      </Card>
    </>
  );
}
