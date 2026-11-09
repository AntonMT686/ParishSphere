import ConstructionIcon from '@mui/icons-material/ConstructionOutlined';
import Card from '@mui/material/Card';
import { useTranslation } from 'react-i18next';
import { EmptyState, PageHeader } from '@/design-system';
import type { NavItem } from '@/layouts/navigation';

/** Route target for navigation entries whose module is scheduled in a later roadmap task. */
export function ScheduledModulePage({ item }: { item: NavItem }) {
  const { t } = useTranslation();
  const title = t(`nav.${item.key}`);
  return (
    <>
      <PageHeader title={title} breadcrumbs={[{ label: t('nav.dashboard'), to: '/' }, { label: title }]} />
      <Card>
        <EmptyState
          icon={<ConstructionIcon />}
          title={title}
          description={`This module is delivered in roadmap task ${item.task ?? ''} (docs/09-roadmap-and-testing.md).`}
        />
      </Card>
    </>
  );
}
