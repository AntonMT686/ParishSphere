import { createBrowserRouter, Outlet, type RouteObject } from 'react-router-dom';
import { RedirectIfAuthenticated, RequireAuth, RequirePermission } from '@/auth/guards';
import { ProfilePage } from '@/features/account/ProfilePage';
import { AuditLogPage } from '@/features/admin/AuditLogPage';
import { RoleDetailPage } from '@/features/admin/RoleDetailPage';
import { RolesPage } from '@/features/admin/RolesPage';
import { UsersPage } from '@/features/admin/UsersPage';
import { ChangePasswordPage } from '@/features/auth/ChangePasswordPage';
import { ForgotPasswordPage } from '@/features/auth/ForgotPasswordPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { ResetPasswordPage } from '@/features/auth/ResetPasswordPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { NotFoundPage } from '@/features/NotFoundPage';
import { NotificationsPage } from '@/features/notifications/NotificationsPage';
import { OrgTypesPage } from '@/features/org/OrgTypesPage';
import { FamiliesPage } from '@/features/people/FamiliesPage';
import { FamilyDetailPage } from '@/features/people/FamilyDetailPage';
import { MembersPage } from '@/features/people/MembersPage';
import { RegisterFamilyPage } from '@/features/people/RegisterFamilyPage';
import { OrgUnitDetailPage } from '@/features/org/OrgUnitDetailPage';
import { OrgUnitListPage } from '@/features/org/OrgUnitListPage';
import { ParishSettingsPage } from '@/features/parish/ParishSettingsPage';
import { PriestDetailPage } from '@/features/parish/PriestDetailPage';
import { PriestsPage } from '@/features/parish/PriestsPage';
import { ScheduledModulePage } from '@/features/ScheduledModulePage';
import { AdminLayout } from '@/layouts/AdminLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import { ALL_NAV_ITEMS } from '@/layouts/navigation';

function guarded(permission: string | string[], element: React.ReactNode) {
  return <RequirePermission anyOf={permission}>{element}</RequirePermission>;
}

export const routes: RouteObject[] = [
  {
    element: <AuthLayout />,
    children: [
      { path: '/login', element: <RedirectIfAuthenticated><LoginPage /></RedirectIfAuthenticated> },
      { path: '/forgot-password', element: <RedirectIfAuthenticated><ForgotPasswordPage /></RedirectIfAuthenticated> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      { element: <AuthLayout />, children: [{ path: '/change-password', element: <ChangePasswordPage /> }] },
      {
        element: <AdminLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: '/profile', element: <ProfilePage /> },
          { path: '/notifications', element: <NotificationsPage /> },
          { path: '/admin/users', element: guarded('user.view', <UsersPage />) },
          { path: '/admin/roles', element: guarded('role.view', <RolesPage />) },
          { path: '/admin/roles/:roleId', element: guarded('role.view', <RoleDetailPage />) },
          { path: '/admin/audit', element: guarded('audit.view', <AuditLogPage />) },
          { path: '/families', element: guarded('family.view', <FamiliesPage />) },
          { path: '/families/new', element: guarded('family.create', <RegisterFamilyPage />) },
          { path: '/families/:familyId', element: guarded('family.view', <FamilyDetailPage />) },
          { path: '/members', element: guarded('member.view', <MembersPage />) },
          { path: '/admin/priests', element: guarded('priest.view', <PriestsPage />) },
          { path: '/admin/priests/:priestId', element: guarded('priest.view', <PriestDetailPage />) },
          { path: '/admin/settings', element: guarded('settings.view', <ParishSettingsPage />) },
          { path: '/admin/org-types', element: guarded('org_unit.update', <OrgTypesPage />) },
          { path: '/org/units/:unitId', element: guarded('org_unit.view', <OrgUnitDetailPage />) },
          { path: '/org/:typeCode', element: guarded('org_unit.view', <OrgUnitListPage />) },
          ...ALL_NAV_ITEMS.filter((i) => i.task).map((item) => ({
            path: item.path,
            element: item.permission ? guarded(item.permission, <ScheduledModulePage item={item} />) : <ScheduledModulePage item={item} />,
          })),
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const appRoutes: RouteObject[] = [{ element: <Outlet />, children: routes }];

export const router = createBrowserRouter(appRoutes);
