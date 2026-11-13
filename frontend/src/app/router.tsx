import { createBrowserRouter, Outlet, type RouteObject } from 'react-router-dom';
import { RedirectIfAuthenticated, RequireAuth, RequirePermission } from '@/auth/guards';
import { ProfilePage } from '@/features/account/ProfilePage';
import { ActionItemsPage } from '@/features/activities/ActionItemsPage';
import { ActivitiesPage } from '@/features/activities/ActivitiesPage';
import { ActivityDetailPage } from '@/features/activities/ActivityDetailPage';
import { ActivityFormPage } from '@/features/activities/ActivityFormPage';
import { CalendarPage } from '@/features/activities/CalendarPage';
import { MeetingDetailPage } from '@/features/activities/MeetingDetailPage';
import { MeetingsPage } from '@/features/activities/MeetingsPage';
import { AuditLogPage } from '@/features/admin/AuditLogPage';
import { NoticeDetailPage } from '@/features/notices/NoticeDetailPage';
import { NoticeFormPage } from '@/features/notices/NoticeFormPage';
import { NoticesPage } from '@/features/notices/NoticesPage';
import { AccountsPage } from '@/features/finance/AccountsPage';
import { StatementPage } from '@/features/finance/StatementPage';
import { StatementsPage } from '@/features/finance/StatementsPage';
import { TransactionDetailPage } from '@/features/finance/TransactionDetailPage';
import { TransactionsPage } from '@/features/finance/TransactionsPage';
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
import { ApprovalDetailPage } from '@/features/workflow/ApprovalDetailPage';
import { MyApprovalsPage } from '@/features/workflow/MyApprovalsPage';
import { SubmittedPage } from '@/features/workflow/SubmittedPage';
import { WorkflowDesignerPage } from '@/features/workflow/WorkflowDesignerPage';
import { WorkflowsPage } from '@/features/workflow/WorkflowsPage';
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
          { path: '/calendar', element: guarded(['activity.view', 'meeting.view'], <CalendarPage />) },
          { path: '/activities', element: guarded('activity.view', <ActivitiesPage />) },
          { path: '/activities/new', element: guarded('activity.create', <ActivityFormPage />) },
          { path: '/activities/:activityId', element: guarded('activity.view', <ActivityDetailPage />) },
          { path: '/activities/:activityId/edit', element: guarded('activity.update', <ActivityFormPage />) },
          { path: '/meetings', element: guarded('meeting.view', <MeetingsPage />) },
          { path: '/meetings/:meetingId', element: guarded('meeting.view', <MeetingDetailPage />) },
          { path: '/action-items', element: <ActionItemsPage /> },
          { path: '/finance/transactions', element: guarded(['finance.view', 'finance.create'], <TransactionsPage />) },
          { path: '/finance/transactions/:txnId', element: guarded(['finance.view', 'finance.create'], <TransactionDetailPage />) },
          { path: '/finance/accounts', element: guarded(['finance.view', 'finance.configure'], <AccountsPage />) },
          { path: '/finance/statements', element: guarded('finance_period.view', <StatementsPage />) },
          { path: '/finance/statements/:periodKey', element: guarded('finance_period.view', <StatementPage />) },
          { path: '/notices', element: guarded('notice.view', <NoticesPage />) },
          { path: '/notices/new', element: guarded('notice.create', <NoticeFormPage />) },
          { path: '/notices/:noticeId', element: guarded('notice.view', <NoticeDetailPage />) },
          { path: '/notices/:noticeId/edit', element: guarded('notice.update', <NoticeFormPage />) },
          { path: '/approvals', element: <MyApprovalsPage /> },
          { path: '/approvals/submitted', element: <SubmittedPage /> },
          { path: '/approvals/:instanceId', element: <ApprovalDetailPage /> },
          { path: '/admin/workflows', element: guarded('workflow.view', <WorkflowsPage />) },
          { path: '/admin/workflows/new', element: guarded('workflow.manage', <WorkflowDesignerPage />) },
          { path: '/admin/workflows/:definitionId', element: guarded('workflow.view', <WorkflowDesignerPage />) },
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
