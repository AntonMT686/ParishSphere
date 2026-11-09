import NotificationsIcon from '@mui/icons-material/NotificationsOutlined';
import Badge from '@mui/material/Badge';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import Popover from '@mui/material/Popover';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import { useMarkAllRead, useNotifications, useUnreadCount } from './api';
import { NotificationItemRow } from './NotificationItemRow';

export function NotificationsBell() {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { data: unread = 0 } = useUnreadCount();
  const { data } = useNotifications(1, 6, false);
  const markAll = useMarkAllRead();
  return (
    <>
      <IconButton aria-label={t('notifications.title')} onClick={(e) => setAnchor(e.currentTarget)}>
        <Badge color="error" badgeContent={unread} max={99}>
          <NotificationsIcon />
        </Badge>
      </IconButton>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        slotProps={{ paper: { sx: { width: 380, maxWidth: 'calc(100vw - 32px)' } } }}
      >
        <Stack direction="row" alignItems="center" sx={{ px: 2, py: 1.5 }}>
          <Typography variant="h4" sx={{ flexGrow: 1 }}>
            {t('notifications.title')}
          </Typography>
          {unread > 0 && (
            <Button size="small" onClick={() => markAll.mutate()}>
              {t('notifications.markAllRead')}
            </Button>
          )}
        </Stack>
        <Divider />
        <Box sx={{ maxHeight: 420, overflowY: 'auto', p: 1 }}>
          {data?.items.length ? (
            <List dense disablePadding>
              {data.items.map((n) => (
                <NotificationItemRow key={n.id} n={n} onNavigate={() => setAnchor(null)} />
              ))}
            </List>
          ) : (
            <Typography color="text.secondary" sx={{ p: 3, textAlign: 'center' }}>
              {t('notifications.empty')}
            </Typography>
          )}
        </Box>
        <Divider />
        <Button fullWidth component={RouterLink} to="/notifications" onClick={() => setAnchor(null)} sx={{ py: 1.25 }}>
          {t('common.viewAll')}
        </Button>
      </Popover>
    </>
  );
}
