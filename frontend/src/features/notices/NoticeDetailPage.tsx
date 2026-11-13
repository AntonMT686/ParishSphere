import EditIcon from '@mui/icons-material/EditOutlined';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdfOutlined';
import SendIcon from '@mui/icons-material/SendOutlined';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Grid from '@mui/material/Grid2';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Notice } from '@/api/types';
import { EmptyState, PageHeader, StatusBadge, useFeedback } from '@/design-system';
import { ApprovalSection, AttachmentsCard } from '@/features/activities/shared';
import { downloadBlob } from '@/features/finance/api';
import { wfKeys } from '@/features/workflow/api';
import { formatWallTime } from '@/lib/format';
import { CATEGORY_COLOR, noticeKeys, useNotice } from './api';

export function NoticeDetailPage() {
  const { noticeId = '' } = useParams();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { toast, toastError, confirm } = useFeedback();
  const { data: n, isError } = useNotice(noticeId);
  const [lang, setLang] = useState<'en' | 'ta' | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: noticeKeys.all });
  const act = useMutation({
    mutationFn: async (what: 'submit' | 'publish' | 'archive') => (await api.post<Notice>(`/notices/${noticeId}/${what}`, what === 'submit' ? {} : undefined)).data,
    onSuccess: (x, what) => { qc.setQueryData([...noticeKeys.all, x.id], x); refresh(); void qc.invalidateQueries({ queryKey: wfKeys.all }); toast(t(`notices.done.${what}`)); },
    onError: toastError,
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/notices/${noticeId}`),
    onSuccess: () => { refresh(); navigate('/notices', { replace: true }); },
    onError: toastError,
  });
  if (isError) return <EmptyState title={t('notices.notFound')} />;
  if (!n) return <Skeleton variant="rounded" height={420} />;
  const hasLocal = Boolean(n.title_local || n.body_local);
  const shown = lang ?? (i18n.language === 'ta' && hasLocal ? 'ta' : 'en');
  const title = shown === 'ta' && n.title_local ? n.title_local : n.title;
  const body = shown === 'ta' && n.body_local ? n.body_local : n.body;
  const manager = n.can.edit || n.can.publish || n.can.archive || n.can.delete || n.state !== 'LIVE';
  return (
    <>
      <PageHeader
        title={title}
        subtitle={`${t(`notices.category.${n.category}`)} · ${n.code}`}
        breadcrumbs={[{ label: t('nav.content') }, { label: t('nav.notices'), to: '/notices' }, { label: n.code }]}
        actions={
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {n.can.delete && <Button color="error" onClick={async () => { if (await confirm({ title: t('notices.deleteConfirm'), destructive: true })) remove.mutate(); }}>{t('common.delete')}</Button>}
            {n.can.archive && <Button color="inherit" onClick={async () => { if (await confirm({ title: t('notices.archiveConfirm'), message: t('notices.archiveHint') })) act.mutate('archive'); }}>{t('notices.archive')}</Button>}
            <Button startIcon={<PictureAsPdfIcon />} onClick={() => downloadBlob(`/notices/${n.id}/pdf`, `notice-${n.code}.pdf`).catch(toastError)}>{t('notices.printOne')}</Button>
            {n.can.edit && <Button startIcon={<EditIcon />} component={RouterLink} to={`/notices/${n.id}/edit`}>{t('common.edit')}</Button>}
            {n.can.publish && <Button variant="contained" onClick={() => act.mutate('publish')}>{t('notices.publishNow')}</Button>}
            {n.can.submit && <Button variant="contained" startIcon={<SendIcon />} disabled={act.isPending} onClick={() => act.mutate('submit')}>
              {n.status === 'REWORK' ? t('activities.resubmit') : t('activities.submit')}</Button>}
          </Stack>
        }
      />
      {n.state === 'SCHEDULED' && <Alert severity="info" sx={{ mb: 2 }}>{t('notices.scheduledBanner', { when: formatWallTime(n.publish_at) })}</Alert>}
      {n.state === 'EXPIRED' && <Alert severity="warning" sx={{ mb: 2 }}>{t('notices.expiredBanner')}</Alert>}
      {n.status === 'REWORK' && <Alert severity="warning" sx={{ mb: 2 }}>{t('activities.reworkBanner')}</Alert>}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: manager ? 7 : 12 }}>
          <Card sx={{ borderColor: n.is_important ? 'error.main' : undefined, borderWidth: n.is_important ? 2 : 1 }}>
            <CardContent>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
                <Chip size="small" color={CATEGORY_COLOR[n.category] ?? 'default'} label={t(`notices.category.${n.category}`)} />
                {n.is_important && <Chip size="small" color="error" label={t('notices.important')} />}
                <StatusBadge status={n.state} />
                {hasLocal && (
                  <ToggleButtonGroup size="small" exclusive value={shown} onChange={(_e, v) => v && setLang(v)} sx={{ ml: 'auto' }} aria-label={t('notices.language')}>
                    <ToggleButton value="en">English</ToggleButton><ToggleButton value="ta">தமிழ்</ToggleButton>
                  </ToggleButtonGroup>
                )}
              </Stack>
              <Typography variant="body1" sx={{ whiteSpace: 'pre-line', lineHeight: 1.7 }}>{body}</Typography>
              <Divider sx={{ my: 2 }} />
              <Typography variant="caption" color="text.secondary" component="div">
                {t('notices.publishedFor', { when: formatWallTime(n.publish_at) })}{n.expires_at ? ` · ${t('notices.until', { when: formatWallTime(n.expires_at) })}` : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary" component="div">
                {t('notices.audience')}: {n.audience_all ? t('notices.everyone') : n.audience.map((a) => a.name).join(', ')}{n.is_public ? ` · ${t('notices.onPortal')}` : ''}
                {n.created_by ? ` · ${t('notices.preparedByName', { name: n.created_by })}` : ''}
              </Typography>
            </CardContent>
          </Card>
          {!manager && n.attachments > 0 && <div style={{ marginTop: 16 }}><AttachmentsCard base={`/notices/${n.id}`} canAdd={false} canRemove={false} /></div>}
        </Grid>
        {manager && (
          <Grid size={{ xs: 12, lg: 5 }}>
            <Stack spacing={2}>
              <ApprovalSection entityType="NOTICE" entityId={n.id} onChange={refresh} />
              <AttachmentsCard base={`/notices/${n.id}`} canAdd={n.can.edit} canRemove={n.can.edit} />
            </Stack>
          </Grid>
        )}
      </Grid>
    </>
  );
}
