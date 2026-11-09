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
import GroupsIcon from '@mui/icons-material/GroupsOutlined';
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
  path: string;
  icon: ReactNode;
  /** Task in docs/09-roadmap-and-testing.md that delivers this screen. */
  task?: string;
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
      { key: 'calendar', path: '/calendar', icon: <EventIcon />, task: 'T11' },
    ],
  },
  {
    key: 'people',
    items: [
      { key: 'families', path: '/families', icon: <FamilyIcon />, task: 'T8' },
      { key: 'members', path: '/members', icon: <PeopleIcon />, task: 'T8' },
      { key: 'registers', path: '/registers', icon: <MenuBookIcon />, task: 'T21' },
    ],
  },
  {
    key: 'organisations',
    items: [
      { key: 'council', path: '/org/council', icon: <ChurchIcon />, task: 'T7' },
      { key: 'committees', path: '/org/committees', icon: <HubIcon />, task: 'T7' },
      { key: 'anbiyam', path: '/org/anbiyam', icon: <GroupsIcon />, task: 'T7' },
      { key: 'sabai', path: '/org/sabai', icon: <GroupsIcon />, task: 'T7' },
      { key: 'societies', path: '/org/societies', icon: <GroupsIcon />, task: 'T7' },
    ],
  },
  {
    key: 'activities',
    items: [
      { key: 'activityList', path: '/activities', icon: <ChecklistIcon />, task: 'T11' },
      { key: 'meetings', path: '/meetings', icon: <EventIcon />, task: 'T11' },
      { key: 'actionItems', path: '/action-items', icon: <TaskIcon />, task: 'T11' },
    ],
  },
  {
    key: 'approvals',
    items: [
      { key: 'myApprovals', path: '/approvals', icon: <FactCheckIcon />, task: 'T10' },
      { key: 'submitted', path: '/approvals/submitted', icon: <HistoryIcon />, task: 'T10' },
    ],
  },
  {
    key: 'finance',
    items: [
      { key: 'transactions', path: '/finance/transactions', icon: <ReceiptIcon />, task: 'T12' },
      { key: 'statements', path: '/finance/statements', icon: <AssessmentIcon />, task: 'T12' },
      { key: 'accounts', path: '/finance/accounts', icon: <AccountBalanceIcon />, task: 'T12' },
    ],
  },
  {
    key: 'content',
    items: [
      { key: 'notices', path: '/notices', icon: <CampaignIcon />, task: 'T13' },
      { key: 'documents', path: '/documents', icon: <DescriptionIcon />, task: 'T20' },
    ],
  },
  { key: 'reports', items: [{ key: 'reports', path: '/reports', icon: <AssessmentIcon />, task: 'T15' }] },
  {
    key: 'administration',
    items: [
      { key: 'users', path: '/admin/users', icon: <PeopleIcon />, task: 'T4' },
      { key: 'roles', path: '/admin/roles', icon: <SecurityIcon />, task: 'T4' },
      { key: 'workflows', path: '/admin/workflows', icon: <RouteIcon />, task: 'T10' },
      { key: 'orgTypes', path: '/admin/org-types', icon: <HubIcon />, task: 'T7' },
      { key: 'priests', path: '/admin/priests', icon: <ChurchIcon />, task: 'T9' },
      { key: 'settings', path: '/admin/settings', icon: <SettingsIcon />, task: 'T9' },
      { key: 'audit', path: '/admin/audit', icon: <HistoryIcon />, task: 'T15' },
    ],
  },
];

export const ALL_NAV_ITEMS: NavItem[] = NAVIGATION.flatMap((s) => s.items);
