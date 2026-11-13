import SearchIcon from '@mui/icons-material/Search';
import Box from '@mui/material/Box';
import ClickAwayListener from '@mui/material/ClickAwayListener';
import InputBase from '@mui/material/InputBase';
import LinearProgress from '@mui/material/LinearProgress';
import Paper from '@mui/material/Paper';
import Popper from '@mui/material/Popper';
import Typography from '@mui/material/Typography';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { SearchHit } from '@/api/types';
import { StatusBadge } from '@/design-system';
import { useDebounced, useSearch } from './api';

/** Top-bar search: type two letters, pick a result with the arrow keys and Enter; Ctrl+K or "/" focuses it. */
export function GlobalSearch() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const listId = useId();
  const anchor = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const term = useDebounced(q);
  const { data: raw, isFetching } = useSearch(term);
  const ready = term.trim().length >= 2 && q.trim().length >= 2;
  // Only results for the text currently typed: stale results must never be clickable.
  const data = raw && raw.q === q.trim() ? raw : undefined;
  const hits = useMemo(() => (ready ? (data?.groups.flatMap((g) => g.hits) ?? []) : []), [data, ready]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && (e.target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName));
      if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  useEffect(() => setActive(-1), [term]);

  const go = (path: string) => {
    setOpen(false);
    setQ('');
    input.current?.blur();
    navigate(path);
  };
  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((i) => Math.min(i + 1, hits.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(i - 1, -1)); }
    else if (e.key === 'Escape') { setOpen(false); input.current?.blur(); }
    else if (e.key === 'Enter' && q.trim().length >= 2) {
      e.preventDefault();
      const hit = hits[active];
      go(hit ? hit.link : `/search?q=${encodeURIComponent(q.trim())}`);
    }
  };
  let index = -1;
  const option = (h: SearchHit) => {
    index += 1;
    const i = index;
    return (
      <Box key={`${h.link}`} id={`${listId}-${i}`} role="option" aria-selected={i === active}
        onMouseEnter={() => setActive(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => go(h.link)}
        sx={{ px: 2, py: 0.75, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 1, bgcolor: i === active ? 'action.selected' : undefined }}>
        <Box sx={{ minWidth: 0, flexGrow: 1 }}>
          <Typography variant="body2" fontWeight={600} noWrap>{h.title}</Typography>
          <Typography variant="caption" color="text.secondary" noWrap component="div">{[h.code, h.subtitle].filter(Boolean).join(' · ')}</Typography>
        </Box>
        {h.status && h.status !== 'ACTIVE' && <StatusBadge status={h.status} />}
      </Box>
    );
  };

  return (
    <ClickAwayListener onClickAway={() => setOpen(false)}>
      <Box ref={anchor} role="search" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 0.5, borderRadius: 2, bgcolor: 'action.hover', flexGrow: 1, maxWidth: 520, minWidth: 0, position: 'relative' }}>
        <SearchIcon fontSize="small" color="action" />
        <InputBase inputRef={input} value={q} fullWidth placeholder={t('search.placeholder')}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onKeyDown={onKeyDown}
          inputProps={{ 'aria-label': t('common.search'), role: 'combobox', 'aria-expanded': open && ready, 'aria-controls': listId, 'aria-autocomplete': 'list',
            'aria-activedescendant': active >= 0 ? `${listId}-${active}` : undefined }} />
        <Popper open={open && ready} anchorEl={anchor.current} placement="bottom-start" sx={{ zIndex: (th) => th.zIndex.modal, width: { xs: 'calc(100vw - 32px)', sm: Math.max(anchor.current?.offsetWidth ?? 0, 420) } }}>
          <Paper elevation={8} sx={{ mt: 0.5, maxHeight: '70vh', overflowY: 'auto', py: 1 }}>
            {isFetching && <LinearProgress sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2 }} />}
            <Box id={listId} role="listbox" aria-label={t('search.results')}>
              {data?.groups.map((g) => (
                <Box key={g.key} role="group" aria-label={t(`search.groups.${g.key}`)}>
                  <Typography variant="overline" color="text.secondary" sx={{ px: 2, display: 'block' }}>
                    {t(`search.groups.${g.key}`)} · {g.total}
                  </Typography>
                  {g.hits.map(option)}
                </Box>
              ))}
            </Box>
            {data && data.groups.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ px: 2, py: 1 }}>{t('search.noResults', { q: term.trim() })}</Typography>
            )}
            {data && data.groups.length > 0 && (
              <Typography component="div" variant="body2" color="primary" onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(`/search?q=${encodeURIComponent(q.trim())}`)} sx={{ px: 2, pt: 1, cursor: 'pointer', borderTop: 1, borderColor: 'divider', mt: 1 }}>
                {t('search.seeAll')}
              </Typography>
            )}
          </Paper>
        </Popper>
      </Box>
    </ClickAwayListener>
  );
}
