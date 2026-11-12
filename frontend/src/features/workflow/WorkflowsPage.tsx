import AddIcon from '@mui/icons-material/Add';
import ArrowForwardIcon from '@mui/icons-material/ArrowForwardIos';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { api } from '@/api/client';
import type { WorkflowDefinition } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { formatMoney } from '@/lib/format';
import { ENTITY_TYPE_CODES, useDefinitions, wfKeys } from './api';

function conditionChips(d: Pick<WorkflowDefinition, 'conditions'>, t: (k: string) => string): string[] {
  const c = d.conditions;
  const out: string[] = [];
  if (c.org_unit_types?.length) out.push(c.org_unit_types.join(', '));
  if (c.parish_level === true) out.push(t('workflow.parishLevelOnly'));
  if (c.parish_level === false) out.push(t('workflow.orgLevelOnly'));
  if (c.categories?.length) out.push(c.categories.join(', '));
  if (c.min_amount != null) out.push(`≥ ${formatMoney(c.min_amount)}`);
  if (c.max_amount != null) out.push(`≤ ${formatMoney(c.max_amount)}`);
  return out;
}

function DefinitionCard({ d }: { d: WorkflowDefinition }) {
  const { t } = useTranslation();
  const can = useCan();
  const qc = useQueryClient();
  const { toast, toastError } = useFeedback();
  const toggle = useMutation({
    mutationFn: () => api.post(`/workflow/definitions/${d.id}/${d.is_active ? 'deactivate' : 'activate'}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: wfKeys.definitions }); toast(t('common.saved')); },
    onError: toastError,
  });
  return (
    <Card sx={{ opacity: d.is_active ? 1 : 0.65 }}>
      <Stack direction="row" alignItems="stretch">
        <CardActionArea component={RouterLink} to={`/admin/workflows/${d.id}`} sx={{ flexGrow: 1 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="subtitle1" fontWeight={600}>{d.name}</Typography>
              <Chip size="small" variant="outlined" label={`v${d.version}`} />
              {!d.is_active && <Chip size="small" label={t('workflow.inactive')} />}
              {d.priority > 0 && <Chip size="small" variant="outlined" label={t('workflow.priorityN', { n: d.priority })} />}
              {conditionChips(d, t).map((c) => <Chip key={c} size="small" color="info" variant="outlined" label={c} />)}
            </Stack>
            <Stack direction="row" spacing={0.5} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mt: 1.25 }}>
              {d.stages.map((s, i) => (
                <Stack key={s.key ?? i} direction="row" spacing={0.5} alignItems="center">
                  {i > 0 && <ArrowForwardIcon sx={{ fontSize: 12, color: 'text.disabled' }} />}
                  <Chip size="small" label={s.name} color={s.kind === 'APPROVE' ? 'primary' : 'default'}
                    variant={s.optional ? 'outlined' : 'filled'} />
                </Stack>
              ))}
            </Stack>
            {d.running > 0 && (
              <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>{t('workflow.runningN', { count: d.running })}</Typography>
            )}
          </CardContent>
        </CardActionArea>
        {can('workflow.manage') && (
          <Box sx={{ display: 'flex', alignItems: 'center', pr: 1 }}>
            <Tooltip title={d.is_active ? t('workflow.deactivate') : t('workflow.activate')}>
              <Switch checked={d.is_active} disabled={toggle.isPending} onChange={() => toggle.mutate()}
                slotProps={{ input: { 'aria-label': `${d.name}: ${t('workflow.active')}` } }} />
            </Tooltip>
          </Box>
        )}
      </Stack>
    </Card>
  );
}

export function WorkflowsPage() {
  const { t } = useTranslation();
  const can = useCan();
  const { data } = useDefinitions();
  return (
    <>
      <PageHeader
        title={t('nav.workflows')}
        subtitle={t('workflow.adminSubtitle')}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.workflows') }]}
        actions={can('workflow.manage') && (
          <Button variant="contained" startIcon={<AddIcon />} component={RouterLink} to="/admin/workflows/new">{t('workflow.newWorkflow')}</Button>
        )}
      />
      {!data ? <Skeleton variant="rounded" height={360} /> : (
        <Stack spacing={3}>
          {ENTITY_TYPE_CODES.map((code) => {
            const defs = data.filter((d) => d.entity_type === code);
            return (
              <section key={code} aria-label={t(`workflow.entity.${code}`)}>
                <Typography variant="h3" sx={{ mb: 1.25 }}>{t(`workflow.entity.${code}`)}</Typography>
                {defs.length === 0
                  ? <Typography variant="body2" color="text.secondary">{t('workflow.noneForType')}</Typography>
                  : <Stack spacing={1.25}>{defs.map((d) => <DefinitionCard key={d.id} d={d} />)}</Stack>}
              </section>
            );
          })}
          <Typography variant="caption" color="text.secondary">{t('workflow.selectionHint')}</Typography>
        </Stack>
      )}
    </>
  );
}
