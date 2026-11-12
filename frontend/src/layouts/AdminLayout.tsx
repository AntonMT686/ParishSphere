import DarkModeIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeIcon from '@mui/icons-material/LightModeOutlined';
import MenuIcon from '@mui/icons-material/Menu';
import SearchIcon from '@mui/icons-material/Search';
import TranslateIcon from '@mui/icons-material/Translate';
import ChurchIcon from '@mui/icons-material/ChurchOutlined';
import GroupsIcon from '@mui/icons-material/GroupsOutlined';
import HubIcon from '@mui/icons-material/HubOutlined';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import InputBase from '@mui/material/InputBase';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { alpha, useTheme } from '@mui/material/styles';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, Link as RouterLink, useLocation } from 'react-router-dom';
import { useTenantBranding } from '@/api/tenant';
import { useUiStore } from '@/app/uiStore';
import { useCan } from '@/auth/authStore';
import { IdleTimeoutDialog } from '@/auth/IdleTimeoutDialog';
import { NotificationsBell } from '@/features/notifications/NotificationsBell';
import { SUPPORTED_LANGUAGES } from '@/i18n';
import { useOrgTypes, typePath } from '@/features/org/api';
import { useTaskSummary } from '@/features/workflow/api';
import { visibleNavigation, type NavItem } from './navigation';
import { UserMenu } from './UserMenu';

export const SIDEBAR_WIDTH = 264;

function isActive(pathname: string, path: string): boolean {
  return path === '/' ? pathname === '/' : pathname === path || pathname.startsWith(`${path}/`);
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const { data: branding } = useTenantBranding();
  const can = useCan();
  const { i18n } = useTranslation();
  const { data: orgTypes } = useOrgTypes();
  const { data: tasks } = useTaskSummary();
  const orgItems: NavItem[] = (orgTypes ?? []).map((ot) => ({
    key: ot.code,
    label: i18n.language === 'ta' && ot.name_local ? ot.name_local : ot.name_plural,
    path: typePath(ot.code),
    icon: ot.code === 'COUNCIL' ? <ChurchIcon /> : ot.code === 'COMMITTEE' ? <HubIcon /> : <GroupsIcon />,
    permission: 'org_unit.view',
  }));
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ px: 2.5, py: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box component="img" src={branding?.logo_url ?? '/favicon.svg'} alt="" sx={{ width: 36, height: 36 }} />
        <Box sx={{ minWidth: 0 }}>
          <Typography fontWeight={700} noWrap>
            {branding?.display_name ?? t('app.name')}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap component="p">
            {branding?.diocese_name ?? t('app.name')}
          </Typography>
        </Box>
      </Box>
      <Box component="nav" aria-label="Main" sx={{ overflowY: 'auto', flexGrow: 1, px: 1.5, pb: 2 }}>
        {visibleNavigation(can, { organisations: orgItems }).map((section) => (
          <List
            key={section.key}
            dense
            subheader={
              <ListSubheader
                disableSticky
                sx={{ bgcolor: 'transparent', lineHeight: '32px', fontSize: 11, letterSpacing: 0.8 }}
              >
                {t(`nav.${section.key}`).toUpperCase()}
              </ListSubheader>
            }
          >
            {section.items.map((item) => (
              <ListItemButton
                key={item.path}
                component={RouterLink}
                to={item.path}
                selected={isActive(pathname, item.path)}
                onClick={onNavigate}
                sx={{ mb: 0.25 }}
              >
                <ListItemIcon sx={{ minWidth: 36 }}>{item.icon}</ListItemIcon>
                <ListItemText primary={item.label ?? t(`nav.${item.key}`)} primaryTypographyProps={{ fontSize: 14 }} />
                {item.key === 'myApprovals' && Boolean(tasks?.pending) && (
                  <Chip size="small" color={tasks!.overdue ? 'error' : 'primary'} label={tasks!.pending}
                    aria-label={t('workflow.pendingCount', { count: tasks!.pending })} sx={{ height: 20, fontSize: 12 }} />
                )}
              </ListItemButton>
            ))}
          </List>
        ))}
      </Box>
    </Box>
  );
}

export function AdminLayout() {
  const theme = useTheme();
  const { t, i18n } = useTranslation();
  const desktop = useMediaQuery(theme.breakpoints.up('md'));
  const { mode, toggleMode, sidebarOpen, setSidebarOpen } = useUiStore();
  const [langAnchor, setLangAnchor] = useState<HTMLElement | null>(null);

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Drawer
        variant={desktop ? 'permanent' : 'temporary'}
        open={desktop || sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          width: desktop ? SIDEBAR_WIDTH : undefined,
          flexShrink: 0,
          '& .MuiDrawer-paper': { width: SIDEBAR_WIDTH, boxSizing: 'border-box', borderRight: 1, borderColor: 'divider' },
        }}
      >
        <Sidebar onNavigate={desktop ? undefined : () => setSidebarOpen(false)} />
      </Drawer>

      <Box sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <AppBar
          position="sticky"
          elevation={0}
          color="inherit"
          sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: alpha(theme.palette.background.paper, 0.9), backdropFilter: 'blur(8px)' }}
        >
          <Toolbar sx={{ gap: 1 }}>
            {!desktop && (
              <IconButton edge="start" aria-label="Open navigation" onClick={() => setSidebarOpen(true)}>
                <MenuIcon />
              </IconButton>
            )}
            <Box
              role="search"
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                px: 1.5,
                py: 0.5,
                borderRadius: 2,
                bgcolor: 'action.hover',
                flexGrow: 1,
                maxWidth: 520,
              }}
            >
              <SearchIcon fontSize="small" color="action" />
              <InputBase placeholder={t('common.search')} inputProps={{ 'aria-label': t('common.search') }} fullWidth />
            </Box>
            <Box sx={{ flexGrow: 1 }} />
            <Tooltip title={t('common.language')}>
              <IconButton aria-label={t('common.language')} onClick={(e) => setLangAnchor(e.currentTarget)}>
                <TranslateIcon />
              </IconButton>
            </Tooltip>
            <Menu anchorEl={langAnchor} open={Boolean(langAnchor)} onClose={() => setLangAnchor(null)}>
              {SUPPORTED_LANGUAGES.map((l) => (
                <MenuItem
                  key={l.code}
                  selected={i18n.language === l.code}
                  onClick={() => {
                    void i18n.changeLanguage(l.code);
                    setLangAnchor(null);
                  }}
                >
                  {l.label}
                </MenuItem>
              ))}
            </Menu>
            <Tooltip title={t('common.toggleTheme')}>
              <IconButton aria-label={t('common.toggleTheme')} onClick={toggleMode}>
                {mode === 'light' ? <DarkModeIcon /> : <LightModeIcon />}
              </IconButton>
            </Tooltip>
            <NotificationsBell />
            <UserMenu />
          </Toolbar>
        </AppBar>
        <Box component="main" sx={{ p: { xs: 2, md: 3 }, flexGrow: 1, maxWidth: 1600, width: '100%', mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>
      <IdleTimeoutDialog />
    </Box>
  );
}
