import AttachFileIcon from '@mui/icons-material/AttachFile';
import PriorityHighIcon from '@mui/icons-material/PriorityHigh';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { NoticeListItem } from '@/api/types';
import { formatWallTime } from '@/lib/format';
import { CATEGORY_COLOR } from './api';

export function NoticeCard({ n, compact = false }: { n: NoticeListItem; compact?: boolean }) {
  const { t, i18n } = useTranslation();
  const ta = i18n.language === 'ta';
  const title = ta && n.title_local ? n.title_local : n.title;
  const excerpt = ta && n.excerpt_local ? n.excerpt_local : n.excerpt;
  return (
    <Card component="article" aria-label={title}
      sx={{ height: '100%', borderColor: n.is_important ? 'error.main' : undefined, borderWidth: n.is_important ? 2 : 1 }}>
      <CardActionArea component={RouterLink} to={`/notices/${n.id}`} sx={{ height: '100%', alignItems: 'stretch', display: 'flex' }}>
        <CardContent sx={{ flexGrow: 1 }}>
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
            <Chip size="small" color={CATEGORY_COLOR[n.category] ?? 'default'} label={t(`notices.category.${n.category}`)} />
            {n.is_important && <Chip size="small" color="error" variant="outlined" icon={<PriorityHighIcon />} label={t('notices.important')} />}
            {n.attachments > 0 && <AttachFileIcon fontSize="small" color="action" aria-label={t('notices.hasFiles')} />}
          </Stack>
          <Typography variant={compact ? 'subtitle1' : 'h3'} fontWeight={700} sx={{ mb: 0.75 }}>{title}</Typography>
          {!compact && <Typography variant="body2" color="text.secondary" sx={{ mb: 1.25 }}>{excerpt}</Typography>}
          <Typography variant="caption" color="text.secondary">
            {formatWallTime(n.publish_at)}{n.expires_at ? ` · ${t('notices.until', { when: formatWallTime(n.expires_at) })}` : ''}
            {!n.audience_all && n.audience.length > 0 ? ` · ${n.audience.map((a) => a.name).join(', ')}` : ''}
          </Typography>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
