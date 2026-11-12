import AddIcon from '@mui/icons-material/Add';
import ArrowDownIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpIcon from '@mui/icons-material/ArrowUpward';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import Grid from '@mui/material/Grid2';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { AssigneeRule, OrgUnit, UserLookup, WorkflowDefinition, WorkflowPreview, WorkflowStage } from '@/api/types';
import { useCan } from '@/auth/authStore';
import { PageHeader, useFeedback } from '@/design-system';
import { useRoles } from '@/features/admin/api';
import { useOrgTypes } from '@/features/org/api';
import { OrgUnitPicker, UserPicker } from '@/features/org/pickers';
import { formatDateTime } from '@/lib/format';
import { ENTITY_TYPE_CODES, useDefinition, useDefinitions, useEntityTypes, wfKeys } from './api';

type Rule = AssigneeRule & { label?: string };
type Stage = Omit<WorkflowStage, 'assignees' | 'escalate_to'> & { assignees: Rule[]; escalate_to: Rule[] };
interface Draft {
  entity_type: string;
  name: string;
  description: string;
  priority: number;
  conditions: WorkflowDefinition['conditions'];
  stages: Stage[];
}

const newStage = (n: number): Stage => ({
  name: `Stage ${n}`, kind: 'REVIEW', quorum: 'ANY', optional: false, sla_hours: 72, allow_delegation: true,
  assignees: [{ type: 'ROLE', role: 'PARISH_PRIEST', scope: 'PARISH' }], escalate_to: [],
});

function fromDefinition(d: WorkflowDefinition): Draft {
  return {
    entity_type: d.entity_type, name: d.name, description: d.description ?? '', priority: d.priority,
    conditions: d.conditions, stages: d.stages.map((s) => ({ ...s, escalate_to: s.escalate_to ?? [] })),
  };
}

function toPayload(d: Draft) {
  const strip = (r: Rule): AssigneeRule => ({ type: r.type, role: r.role, position: r.position, scope: r.scope, user_id: r.user_id });
  return {
    name: d.name.trim(), description: d.description.trim() || null, priority: d.priority, conditions: d.conditions,
    stages: d.stages.map((s) => ({ ...s, sla_hours: s.sla_hours || null, assignees: s.assignees.map(strip), escalate_to: s.escalate_to.map(strip) })),
  };
}

// ----------------------------------------------------------------------------- rule editor
function RuleRow({ rule, onChange, onDelete }: { rule: Rule; onChange: (r: Rule) => void; onDelete: () => void }) {
  const { t } = useTranslation();
  const { data: roles = [] } = useRoles();
  const { data: types = [] } = useOrgTypes();
  const positions = useMemo(() => {
    const m = new Map<string, string>();
    types.forEach((ty) => ty.positions.forEach((p) => { if (!m.has(p.code)) m.set(p.code, p.name); }));
    return [...m.entries()];
  }, [types]);
  const user: UserLookup | null = rule.type === 'USER' && rule.user_id ? { id: rule.user_id, username: '', full_name: rule.label ?? rule.user_id } : null;
  const setType = (type: Rule['type']) =>
    onChange(type === 'ROLE' ? { type, role: 'PARISH_PRIEST', scope: 'PARISH' }
      : type === 'POSITION' ? { type, position: 'PRESIDENT', scope: 'SAME_ORG_UNIT' } : { type, scope: 'PARISH' });
  return (
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
      <TextField select size="small" label={t('workflow.ruleType')} value={rule.type} onChange={(e) => setType(e.target.value as Rule['type'])} sx={{ minWidth: 150, maxWidth: { md: 170 } }}>
        {(['ROLE', 'POSITION', 'USER'] as const).map((k) => <MenuItem key={k} value={k}>{t(`workflow.rule.${k}`)}</MenuItem>)}
      </TextField>
      {rule.type === 'ROLE' && (
        <TextField select size="small" label={t('workflow.role')} value={rule.role ?? ''} onChange={(e) => onChange({ ...rule, role: e.target.value })}>
          {roles.map((r) => <MenuItem key={r.code} value={r.code}>{r.name}</MenuItem>)}
        </TextField>
      )}
      {rule.type === 'POSITION' && (
        <TextField select size="small" label={t('workflow.position')} value={rule.position ?? ''} onChange={(e) => onChange({ ...rule, position: e.target.value })}>
          {positions.map(([code, name]) => <MenuItem key={code} value={code}>{name}</MenuItem>)}
        </TextField>
      )}
      {rule.type !== 'USER' && (
        <TextField select size="small" label={t('workflow.scope')} value={rule.scope} onChange={(e) => onChange({ ...rule, scope: e.target.value as Rule['scope'] })}>
          {(rule.type === 'ROLE' ? ['PARISH', 'SAME_ORG_UNIT', 'PARENT_ORG_UNIT'] : ['SAME_ORG_UNIT', 'PARENT_ORG_UNIT']).map((s) => (
            <MenuItem key={s} value={s}>{t(`workflow.scopeLabel.${s}`)}</MenuItem>
          ))}
        </TextField>
      )}
      {rule.type === 'USER' && (
        <Box sx={{ flexGrow: 1 }}>
          <UserPicker label={t('workflow.user')} value={user} onChange={(u) => onChange({ type: 'USER', scope: 'PARISH', user_id: u?.id ?? null, label: u?.full_name })} />
        </Box>
      )}
      <Tooltip title={t('common.remove')}>
        <IconButton aria-label={t('common.remove')} onClick={onDelete}><DeleteIcon /></IconButton>
      </Tooltip>
    </Stack>
  );
}

function RuleList({ title, rules, onChange, hint }: { title: string; rules: Rule[]; onChange: (r: Rule[]) => void; hint?: string }) {
  const { t } = useTranslation();
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>{title}</Typography>
      {hint && <Typography variant="caption" color="text.secondary" component="p" sx={{ mb: 1 }}>{hint}</Typography>}
      <Stack spacing={1.25}>
        {rules.map((r, i) => (
          <RuleRow key={i} rule={r} onChange={(nr) => onChange(rules.map((x, j) => (j === i ? nr : x)))} onDelete={() => onChange(rules.filter((_, j) => j !== i))} />
        ))}
      </Stack>
      <Button size="small" startIcon={<AddIcon />} sx={{ mt: 1 }}
        onClick={() => onChange([...rules, { type: 'ROLE', role: 'PARISH_PRIEST', scope: 'PARISH' }])}>{t('workflow.addRule')}</Button>
    </Box>
  );
}

// ----------------------------------------------------------------------------- stage editor
function StageCard({ stage, index, count, onChange, onMove, onDelete }: {
  stage: Stage; index: number; count: number; onChange: (s: Stage) => void; onMove: (dir: -1 | 1) => void; onDelete: () => void;
}) {
  const { t } = useTranslation();
  const quorumMode = stage.quorum === 'ANY' || stage.quorum === 'ALL' ? stage.quorum : 'N';
  return (
    <Card component="section" aria-label={`${t('workflow.stage')} ${index + 1}`}>
      <CardHeader
        title={<Stack direction="row" spacing={1} alignItems="center"><Chip size="small" label={index + 1} color="primary" /><span>{stage.name || t('workflow.stage')}</span></Stack>}
        action={
          <Stack direction="row">
            <IconButton aria-label={t('workflow.moveUp')} disabled={index === 0} onClick={() => onMove(-1)}><ArrowUpIcon /></IconButton>
            <IconButton aria-label={t('workflow.moveDown')} disabled={index === count - 1} onClick={() => onMove(1)}><ArrowDownIcon /></IconButton>
            <IconButton aria-label={t('workflow.removeStage')} disabled={count === 1} onClick={onDelete}><DeleteIcon /></IconButton>
          </Stack>
        }
      />
      <CardContent sx={{ pt: 0 }}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 12, md: 6 }}>
            <TextField label={t('workflow.stageName')} value={stage.name} onChange={(e) => onChange({ ...stage, name: e.target.value })} required />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField select label={t('workflow.stageKind')} value={stage.kind} onChange={(e) => onChange({ ...stage, kind: e.target.value as Stage['kind'] })}>
              <MenuItem value="REVIEW">{t('workflow.kind.REVIEW')}</MenuItem>
              <MenuItem value="APPROVE">{t('workflow.kind.APPROVE')}</MenuItem>
            </TextField>
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <TextField type="number" label={t('workflow.slaHours')} value={stage.sla_hours ?? ''}
              onChange={(e) => onChange({ ...stage, sla_hours: e.target.value === '' ? null : Number(e.target.value) })} helperText={t('workflow.slaHint')} />
          </Grid>
          <Grid size={{ xs: 12, sm: 6, md: 4 }}>
            <TextField select label={t('workflow.quorum')} value={quorumMode}
              onChange={(e) => onChange({ ...stage, quorum: e.target.value === 'N' ? 2 : (e.target.value as 'ANY' | 'ALL') })}>
              <MenuItem value="ANY">{t('workflow.quorumAny')}</MenuItem>
              <MenuItem value="ALL">{t('workflow.quorumAll')}</MenuItem>
              <MenuItem value="N">{t('workflow.quorumSome')}</MenuItem>
            </TextField>
          </Grid>
          {quorumMode === 'N' && (
            <Grid size={{ xs: 12, sm: 6, md: 2 }}>
              <TextField type="number" label={t('workflow.approvalsNeeded')} value={stage.quorum}
                onChange={(e) => onChange({ ...stage, quorum: Math.max(1, Number(e.target.value) || 1) })} />
            </Grid>
          )}
          <Grid size={{ xs: 12, md: quorumMode === 'N' ? 6 : 8 }}>
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <FormControlLabel control={<Switch checked={Boolean(stage.optional)} onChange={(e) => onChange({ ...stage, optional: e.target.checked })} />} label={t('workflow.optional')} />
              <FormControlLabel control={<Switch checked={stage.allow_delegation !== false} onChange={(e) => onChange({ ...stage, allow_delegation: e.target.checked })} />} label={t('workflow.allowDelegation')} />
            </Stack>
          </Grid>
          <Grid size={12}>
            <RuleList title={t('workflow.whoDecides')} hint={t('workflow.whoDecidesHint')} rules={stage.assignees} onChange={(r) => onChange({ ...stage, assignees: r })} />
          </Grid>
          <Grid size={12}>
            <RuleList title={t('workflow.escalateTo')} hint={t('workflow.escalateHint')} rules={stage.escalate_to} onChange={(r) => onChange({ ...stage, escalate_to: r })} />
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------------- preview
function PreviewCard({ draft }: { draft: Draft }) {
  const { t } = useTranslation();
  const { toastError } = useFeedback();
  const [unit, setUnit] = useState<Pick<OrgUnit, 'id' | 'name' | 'code'> | null>(null);
  const [amount, setAmount] = useState('');
  const [result, setResult] = useState<WorkflowPreview | null>(null);
  const run = useMutation({
    mutationFn: async () => (await api.post<WorkflowPreview>('/workflow/preview', {
      entity_type: draft.entity_type, org_unit_id: unit?.id ?? null, amount: amount === '' ? null : Number(amount),
      stages: toPayload(draft).stages,
    })).data,
    onSuccess: setResult,
    onError: toastError,
  });
  return (
    <Card>
      <CardHeader title={t('workflow.preview')} subheader={t('workflow.previewHint')} />
      <CardContent sx={{ pt: 0 }}>
        <Stack spacing={1.5}>
          <OrgUnitPicker label={t('workflow.forOrganisation')} value={unit} onChange={setUnit} />
          <TextField type="number" label={t('workflow.amount')} value={amount} onChange={(e) => setAmount(e.target.value)} />
          <div><Button variant="outlined" onClick={() => run.mutate()} disabled={run.isPending}>{t('workflow.showApprovers')}</Button></div>
          {result && (
            <Stack component="ol" spacing={1} sx={{ pl: 2.5, m: 0 }} aria-label={t('workflow.preview')}>
              {result.stages.map((s) => (
                <li key={s.index}>
                  <Typography variant="body2" fontWeight={600}>{s.name}</Typography>
                  <Typography variant="body2" color={s.skipped || s.fallback ? 'warning.main' : 'text.secondary'}>
                    {s.skipped ? t('workflow.wouldSkip')
                      : `${s.fallback ? `${t('workflow.fallback')}: ` : ''}${s.assignees.map((a) => a.delegated_from ? `${a.name} (${t('workflow.forName', { name: a.delegated_from })})` : a.name).join(', ')}`}
                  </Typography>
                </li>
              ))}
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

// ----------------------------------------------------------------------------- page
export function WorkflowDesignerPage() {
  const { definitionId } = useParams();
  const isNew = !definitionId || definitionId === 'new';
  const { t } = useTranslation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useCan();
  const editable = can('workflow.manage');
  const { toast, toastError } = useFeedback();
  const { data: existing } = useDefinition(isNew ? undefined : definitionId);
  const { data: versions = [] } = useDefinitions(existing?.code);
  const { data: entityTypes = [] } = useEntityTypes();
  const { data: orgTypes = [] } = useOrgTypes();
  const [draft, setDraft] = useState<Draft | null>(null);
  useEffect(() => {
    if (isNew) setDraft({ entity_type: 'ACTIVITY', name: '', description: '', priority: 10, conditions: {}, stages: [newStage(1)] });
    else if (existing) setDraft(fromDefinition(existing));
  }, [isNew, existing]);
  const save = useMutation({
    mutationFn: async (d: Draft) => isNew
      ? (await api.post<WorkflowDefinition>('/workflow/definitions', { entity_type: d.entity_type, ...toPayload(d) })).data
      : (await api.put<WorkflowDefinition>(`/workflow/definitions/${definitionId}`, toPayload(d))).data,
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: wfKeys.definitions });
      toast(isNew ? t('common.saved') : t('workflow.savedVersion', { n: saved.version }));
      navigate(`/admin/workflows/${saved.id}`, { replace: true });
    },
    onError: toastError,
  });
  if (!draft || (!isNew && !existing)) return <Skeleton variant="rounded" height={480} />;
  const readOnly = !editable || (existing ? !existing.is_latest : false);
  const et = entityTypes.find((e) => e.code === draft.entity_type);
  const set = (patch: Partial<Draft>) => setDraft({ ...draft, ...patch });
  const setCond = (patch: Partial<Draft['conditions']>) => set({ conditions: { ...draft.conditions, ...patch } });
  const setStage = (i: number, s: Stage) => set({ stages: draft.stages.map((x, j) => (j === i ? s : x)) });
  const move = (i: number, dir: -1 | 1) => {
    const stages = [...draft.stages];
    [stages[i], stages[i + dir]] = [stages[i + dir]!, stages[i]!];
    set({ stages });
  };
  const valid = draft.name.trim().length >= 2 && draft.stages.every((s) => s.name.trim() && s.assignees.length > 0
    && s.assignees.every((r) => (r.type !== 'USER' || r.user_id)));
  const parishLevel = draft.conditions.parish_level == null ? 'ANY' : draft.conditions.parish_level ? 'PARISH' : 'ORG';

  return (
    <>
      <PageHeader
        title={isNew ? t('workflow.newWorkflow') : draft.name}
        subtitle={existing ? `${existing.code} · v${existing.version}` : undefined}
        breadcrumbs={[{ label: t('nav.administration') }, { label: t('nav.workflows'), to: '/admin/workflows' }, { label: isNew ? t('workflow.newWorkflow') : draft.name }]}
        actions={!readOnly && (
          <Button variant="contained" disabled={!valid || save.isPending} onClick={() => save.mutate(draft)}>
            {isNew ? t('common.save') : t('workflow.saveVersion', { n: (existing?.version ?? 0) + 1 })}
          </Button>
        )}
      />
      {existing && !existing.is_latest && (
        <Alert severity="info" sx={{ mb: 2 }}>{t('workflow.oldVersion')}</Alert>
      )}
      {existing && existing.is_latest && existing.running > 0 && editable && (
        <Alert severity="info" sx={{ mb: 2 }}>{t('workflow.runningKeep', { count: existing.running })}</Alert>
      )}
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Box component="fieldset" disabled={readOnly} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
            <Card sx={{ mb: 2 }}>
              <CardHeader title={t('workflow.general')} />
              <CardContent sx={{ pt: 0 }}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, md: 6 }}>
                    <TextField label={t('common.name')} value={draft.name} onChange={(e) => set({ name: e.target.value })} required />
                  </Grid>
                  <Grid size={{ xs: 12, sm: 8, md: 4 }}>
                    <TextField select label={t('workflow.recordType')} value={draft.entity_type} disabled={!isNew} onChange={(e) => set({ entity_type: e.target.value })}>
                      {ENTITY_TYPE_CODES.map((c) => <MenuItem key={c} value={c}>{t(`workflow.entity.${c}`)}</MenuItem>)}
                    </TextField>
                  </Grid>
                  <Grid size={{ xs: 12, sm: 4, md: 2 }}>
                    <TextField type="number" label={t('workflow.priority')} value={draft.priority} onChange={(e) => set({ priority: Number(e.target.value) || 0 })} />
                  </Grid>
                  <Grid size={12}>
                    <TextField label={t('common.description')} value={draft.description} onChange={(e) => set({ description: e.target.value })} multiline minRows={2} />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
            <Card sx={{ mb: 2 }}>
              <CardHeader title={t('workflow.appliesWhen')} subheader={t('workflow.appliesHint')} />
              <CardContent sx={{ pt: 0 }}>
                <Grid container spacing={2}>
                  <Grid size={{ xs: 12, md: 4 }}>
                    <TextField select label={t('workflow.level')} value={parishLevel}
                      onChange={(e) => setCond({ parish_level: e.target.value === 'ANY' ? null : e.target.value === 'PARISH' })}>
                      <MenuItem value="ANY">{t('workflow.anyLevel')}</MenuItem>
                      <MenuItem value="PARISH">{t('workflow.parishLevelOnly')}</MenuItem>
                      <MenuItem value="ORG">{t('workflow.orgLevelOnly')}</MenuItem>
                    </TextField>
                  </Grid>
                  <Grid size={{ xs: 12, md: 8 }}>
                    <Autocomplete multiple options={orgTypes.map((o) => o.code)} value={draft.conditions.org_unit_types ?? []}
                      getOptionLabel={(c) => orgTypes.find((o) => o.code === c)?.name ?? c}
                      onChange={(_e, v) => setCond({ org_unit_types: v.length ? v : null })}
                      renderInput={(p) => <TextField {...p} label={t('workflow.orgTypes')} placeholder={t('workflow.anyType')} />} />
                  </Grid>
                  {et?.has_category && (
                    <Grid size={12}>
                      <Autocomplete multiple freeSolo options={[]} value={draft.conditions.categories ?? []}
                        onChange={(_e, v) => setCond({ categories: v.length ? (v as string[]) : null })}
                        renderInput={(p) => <TextField {...p} label={t('workflow.categories')} helperText={t('workflow.categoriesHint')} />} />
                    </Grid>
                  )}
                  {et?.has_amount && (
                    <>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField type="number" label={t('workflow.minAmount')} value={draft.conditions.min_amount ?? ''}
                          onChange={(e) => setCond({ min_amount: e.target.value === '' ? null : Number(e.target.value) })} />
                      </Grid>
                      <Grid size={{ xs: 12, sm: 6 }}>
                        <TextField type="number" label={t('workflow.maxAmount')} value={draft.conditions.max_amount ?? ''}
                          onChange={(e) => setCond({ max_amount: e.target.value === '' ? null : Number(e.target.value) })} />
                      </Grid>
                    </>
                  )}
                </Grid>
              </CardContent>
            </Card>
            <Typography variant="h3" sx={{ mb: 1.25 }}>{t('workflow.stages')}</Typography>
            <Stack spacing={2}>
              {draft.stages.map((s, i) => (
                <StageCard key={i} stage={s} index={i} count={draft.stages.length} onChange={(ns) => setStage(i, ns)}
                  onMove={(dir) => move(i, dir)} onDelete={() => set({ stages: draft.stages.filter((_, j) => j !== i) })} />
              ))}
            </Stack>
            {!readOnly && (
              <Button startIcon={<AddIcon />} sx={{ mt: 1.5 }} disabled={draft.stages.length >= 10}
                onClick={() => set({ stages: [...draft.stages, newStage(draft.stages.length + 1)] })}>{t('workflow.addStage')}</Button>
            )}
          </Box>
        </Grid>
        <Grid size={{ xs: 12, lg: 4 }}>
          <Stack spacing={2} sx={{ position: { lg: 'sticky' }, top: { lg: 88 } }}>
            <PreviewCard draft={draft} />
            {versions.length > 0 && (
              <Card>
                <CardHeader title={t('workflow.versions')} />
                <CardContent sx={{ pt: 0 }}>
                  <Stack spacing={1}>
                    {versions.map((v) => (
                      <Stack key={v.id} direction="row" spacing={1} alignItems="center">
                        <Button size="small" component={RouterLink} to={`/admin/workflows/${v.id}`} disabled={v.id === definitionId}>v{v.version}</Button>
                        <Typography variant="caption" color="text.secondary">{formatDateTime(v.created_at)}</Typography>
                        {v.is_latest && <Chip size="small" color="primary" variant="outlined" label={t('workflow.latest')} />}
                      </Stack>
                    ))}
                  </Stack>
                </CardContent>
              </Card>
            )}
          </Stack>
        </Grid>
      </Grid>
    </>
  );
}
