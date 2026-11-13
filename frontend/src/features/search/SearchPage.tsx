import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardHeader from '@mui/material/CardHeader';
import Grid from '@mui/material/Grid2';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SearchIcon from '@mui/icons-material/Search';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import type { SearchGroup } from '@/api/types';
import { EmptyState, PageHeader, StatusBadge } from '@/design-system';
import { useSearch } from './api';

function GroupCard({ g, q }: { g: SearchGroup; q: string }) {
  const { t } = useTranslation();
  const [all, setAll] = useState(false);
  const { data } = useSearch(q, { group: g.key, limit: 50, enabled: all });
  const hits = all ? (data?.groups[0]?.hits ?? g.hits) : g.hits;
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader title={t(`search.groups.${g.key}`)} subheader={t('search.matches', { count: g.total })} titleTypographyProps={{ variant: 'h6' }} />
      <CardContent sx={{ pt: 0 }}>
        <Stack component="ul" spacing={1} sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t(`search.groups.${g.key}`)}>
          {hits.map((h) => (
            <Stack component="li" key={h.link} direction="row" spacing={1} alignItems="center">
              <Stack sx={{ minWidth: 0, flexGrow: 1 }}>
                <Typography component={RouterLink} to={h.link} variant="body2" fontWeight={600} noWrap
                  sx={{ color: 'text.primary', textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}>{h.title}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap>{[h.code, h.subtitle].filter(Boolean).join(' · ')}</Typography>
              </Stack>
              {h.status && h.status !== 'ACTIVE' && <StatusBadge status={h.status} />}
            </Stack>
          ))}
        </Stack>
        {!all && g.total > g.hits.length && (
          <Button size="small" sx={{ mt: 1 }} onClick={() => setAll(true)}>{t('search.showAll', { count: Math.min(g.total, 50) })}</Button>
        )}
      </CardContent>
    </Card>
  );
}

export function SearchPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? '';
  const [text, setText] = useState(q);
  const { data, isLoading } = useSearch(q);
  return (
    <>
      <PageHeader title={t('search.title')} subtitle={q ? t('search.resultsFor', { q }) : undefined} />
      <Stack component="form" direction="row" spacing={1} sx={{ mb: 3, maxWidth: 560 }}
        onSubmit={(e) => { e.preventDefault(); setParams(text.trim() ? { q: text.trim() } : {}); }}>
        <TextField fullWidth value={text} onChange={(e) => setText(e.target.value)} label={t('common.search')} placeholder={t('search.placeholder')} />
        <Button type="submit" variant="contained" startIcon={<SearchIcon />}>{t('common.search')}</Button>
      </Stack>
      {q.trim().length < 2 && <Typography color="text.secondary">{t('search.tooShort')}</Typography>}
      {data && data.groups.length === 0 && !isLoading && (
        <Card><EmptyState icon={<SearchIcon />} title={t('search.noResults', { q })} description={t('search.noResultsHint')} /></Card>
      )}
      <Grid container spacing={2}>
        {data?.groups.map((g) => (
          <Grid key={`${q}-${g.key}`} size={{ xs: 12, md: 6, xl: 4 }}><GroupCard g={g} q={q} /></Grid>
        ))}
      </Grid>
    </>
  );
}
