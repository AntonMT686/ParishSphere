import { createBrowserRouter, type RouteObject } from 'react-router-dom';
import { LoginPage } from '@/features/auth/LoginPage';
import { DashboardPage } from '@/features/dashboard/DashboardPage';
import { NotFoundPage } from '@/features/NotFoundPage';
import { ScheduledModulePage } from '@/features/ScheduledModulePage';
import { AdminLayout } from '@/layouts/AdminLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import { ALL_NAV_ITEMS } from '@/layouts/navigation';

export const routes: RouteObject[] = [
  { element: <AuthLayout />, children: [{ path: '/login', element: <LoginPage /> }] },
  {
    element: <AdminLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      ...ALL_NAV_ITEMS.filter((i) => i.task).map((item) => ({
        path: item.path,
        element: <ScheduledModulePage item={item} />,
      })),
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
