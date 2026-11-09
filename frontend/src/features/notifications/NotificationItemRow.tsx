import CircleIcon from '@mui/icons-material/Circle';
import PriorityIcon from '@mui/icons-material/PriorityHighRounded';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import { useNavigate } from 'react-router-dom';
import type { NotificationItem } from '@/api/types';
import { timeAgo } from '@/lib/format';
import { useMarkRead } from './api';

export function NotificationItemRow({ n, onNavigate }: { n: NotificationItem; onNavigate?: () => void }) {
  const markRead = useMarkRead();
  const navigate = useNavigate();
  return (
    <ListItemButton
      alignItems="flex-start"
      onClick={() => {
        if (!n.is_read) markRead.mutate(n.id);
        if (n.link) {
          onNavigate?.();
          navigate(n.link);
        }
      }}
      sx={{ bgcolor: n.is_read ? 'transparent' : 'action.hover', borderRadius: 1, mb: 0.5 }}
    >
      <ListItemIcon sx={{ minWidth: 28, mt: 0.75 }}>
        {n.is_important ? (
          <PriorityIcon fontSize="small" color="warning" />
        ) : (
          <CircleIcon sx={{ fontSize: 10, color: n.is_read ? 'transparent' : 'primary.main' }} />
        )}
      </ListItemIcon>
      <ListItemText
        primary={n.title}
        secondary={`${n.body} · ${timeAgo(n.created_at)}`}
        primaryTypographyProps={{ fontWeight: n.is_read ? 400 : 600, fontSize: 14 }}
        secondaryTypographyProps={{ fontSize: 13 }}
      />
    </ListItemButton>
  );
}
