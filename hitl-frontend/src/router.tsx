import { Navigate, createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { InboxPage } from './pages/InboxPage';
import { TeamMembersPage } from './pages/TeamMembersPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { AuthGuard } from './components/layout/AuthGuard';

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/reset-password', element: <ResetPasswordPage /> },
  {
    path: '/',
    element: (
      <AuthGuard>
        <App />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/inbox" replace /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'teams/:teamId/members', element: <TeamMembersPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
