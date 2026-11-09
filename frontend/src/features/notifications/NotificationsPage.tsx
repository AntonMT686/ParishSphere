import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import FormControlLabel from '@mui/material/FormControlLabel';
import List from '@mui/material/List';
import Pagination from '@mui/material/Pagination';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EmptyState, PageHeader } from '@/design-system';
import { useMarkAllRead, useNotifications } from './api';
import { NotificationItemRow } from './NotificationItemRow';

export function NotificationsPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const { data } = useNotifications(page, 20, unreadOnly);
  const markAll = useMarkAllRead();
  return (
    <>
      <PageHeader
        title={t('notifications.title')}
        breadcrumbs={[{ label: t('nav.dashboard'), to: '/' }, { label: t('notifications.title') }]}
        actions={<Button onClick={() => markAll.mutate()}>{t('notifications.markAllRead')}</Button>}
      />
      <Card sx={{ p: 2 }}>
        <FormControlLabel
          control={<Switch checked={unreadOnly} onChange={(_, v) => { setUnreadOnly(v); setPage(1); }} />}
          label={t('notifications.unreadOnly')}
        />
        {data?.items.length ? (
          <List>
            {data.items.map((n) => (
              <NotificationItemRow key={n.id} n={n} />
            ))}
          </List>
        ) : (
          <EmptyState title={t('notifications.empty')} />
        )}
        {data && data.pages > 1 && (
          <Stack alignItems="center">
            <Pagination count={data.pages} page={page} onChange={(_, p) => setPage(p)} />
          </Stack>
        )}
      </Card>
    </>
  );
}
