import AccountBalanceIcon from '@mui/icons-material/AccountBalanceOutlined';
import AssessmentIcon from '@mui/icons-material/AssessmentOutlined';
import CampaignIcon from '@mui/icons-material/CampaignOutlined';
import ChecklistIcon from '@mui/icons-material/ChecklistOutlined';
import ChurchIcon from '@mui/icons-material/ChurchOutlined';
import DashboardIcon from '@mui/icons-material/SpaceDashboardOutlined';
import DescriptionIcon from '@mui/icons-material/DescriptionOutlined';
import EventIcon from '@mui/icons-material/EventOutlined';
import FactCheckIcon from '@mui/icons-material/FactCheckOutlined';
import FamilyIcon from '@mui/icons-material/FamilyRestroomOutlined';
import HistoryIcon from '@mui/icons-material/HistoryOutlined';
import HubIcon from '@mui/icons-material/HubOutlined';
import MenuBookIcon from '@mui/icons-material/MenuBookOutlined';
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined';
import ReceiptIcon from '@mui/icons-material/ReceiptLongOutlined';
import RouteIcon from '@mui/icons-material/AltRouteOutlined';
import SecurityIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import SettingsIcon from '@mui/icons-material/SettingsOutlined';
import TaskIcon from '@mui/icons-material/TaskAltOutlined';
import type { ReactNode } from 'react';

export interface NavItem {
  key: string; // i18n key under `nav.`
  /** Literal label (dynamic items) instead of the i18n key. */
  label?: string;
  path: string;
  icon: ReactNode;
  /** Task in docs/09-roadmap-and-testing.md that delivers this screen (absent = implemented). */
  task?: string;
  /** Shown only to users holding any of these permissions (UX only; the API enforces). */
  permission?: string | string[];
}

export interface NavSection {
  key: string;
  items: NavItem[];
}

export const NAVIGATION: NavSection[] = [
  {
    key: 'overview',
    items: [
      { key: 'dashboard', path: '/', icon: <DashboardIcon /> },
      { key: 'calendar', path: '/calendar', icon: <EventIcon />, task: 'T11', permission: ['activity.view', 'meeting.view'] },
    ],
  },
  {
    key: 'people',
    items: [
      { key: 'families', path: '/families', icon: <FamilyIcon />, permission: 'family.view' },
      { key: 'members', path: '/members', icon: <PeopleIcon />, permission: 'member.view' },
      { key: 'registers', path: '/registers', icon: <MenuBookIcon />, task: 'T21', permission: 'sacrament.view' },
    ],
  },
  // Items are generated from the parish's configured organisation types (see AdminLayout).
  { key: 'organisations', items: [] },
  {
    key: 'activities',
    items: [
      { key: 'activityList', path: '/activities', icon: <ChecklistIcon />, task: 'T11', permission: 'activity.view' },
      { key: 'meetings', path: '/meetings', icon: <EventIcon />, task: 'T11', permission: 'meeting.view' },
      { key: 'actionItems', path: '/action-items', icon: <TaskIcon />, task: 'T11', permission: 'action_item.view' },
    ],
  },
  {
    key: 'approvals',
    items: [
      { key: 'myApprovals', path: '/approvals', icon: <FactCheckIcon />, task: 'T10', permission: ['activity.review', 'activity.approve', 'meeting.review', 'meeting.approve', 'finance.review', 'finance.approve', 'notice.review', 'notice.approve', 'finance_period.approve'] },
      { key: 'submitted', path: '/approvals/submitted', icon: <HistoryIcon />, task: 'T10' },
    ],
  },
  {
    key: 'finance',
    items: [
      { key: 'transactions', path: '/finance/transactions', icon: <ReceiptIcon />, task: 'T12', permission: 'finance.view' },
      { key: 'statements', path: '/finance/statements', icon: <AssessmentIcon />, task: 'T12', permission: 'finance_period.view' },
      { key: 'accounts', path: '/finance/accounts', icon: <AccountBalanceIcon />, task: 'T12', permission: 'finance.view' },
    ],
  },
  {
    key: 'content',
    items: [
      { key: 'notices', path: '/notices', icon: <CampaignIcon />, task: 'T13', permission: 'notice.view' },
      { key: 'documents', path: '/documents', icon: <DescriptionIcon />, task: 'T20', permission: 'document.view' },
    ],
  },
  { key: 'reports', items: [{ key: 'reports', path: '/reports', icon: <AssessmentIcon />, task: 'T15', permission: 'report.view' }] },
  {
    key: 'administration',
    items: [
      { key: 'users', path: '/admin/users', icon: <PeopleIcon />, permission: 'user.view' },
      { key: 'roles', path: '/admin/roles', icon: <SecurityIcon />, permission: 'role.view' },
      { key: 'workflows', path: '/admin/workflows', icon: <RouteIcon />, task: 'T10', permission: 'workflow.view' },
      { key: 'orgTypes', path: '/admin/org-types', icon: <HubIcon />, permission: 'org_unit.update' },
      { key: 'priests', path: '/admin/priests', icon: <ChurchIcon />, task: 'T9', permission: 'priest.view' },
      { key: 'settings', path: '/admin/settings', icon: <SettingsIcon />, task: 'T9', permission: 'settings.view' },
      { key: 'audit', path: '/admin/audit', icon: <HistoryIcon />, permission: 'audit.view' },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAVIGATION.flatMap((s) => s.items);

/** Sections and items the current user may see (empty sections are dropped). */
export function visibleNavigation(
  can: (code: string | string[]) => boolean,
  dynamic: Record<string, NavItem[]> = {},
): NavSection[] {
  return NAVIGATION.map((s) => ({
    ...s,
    items: [...s.items, ...(dynamic[s.key] ?? [])].filter((i) => !i.permission || can(i.permission)),
  })).filter((s) => s.items.length > 0);
}
