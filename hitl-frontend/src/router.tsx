import { Navigate, createBrowserRouter } from 'react-router-dom';
import { App } from './App';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { ResetPasswordPage } from './pages/ResetPasswordPage';
import { InboxPage } from './pages/InboxPage';
import { TeamMembersPage } from './pages/TeamMembersPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectWizardPage } from './pages/ProjectWizardPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectDeliverablesPage } from './pages/ProjectDeliverablesPage';
import { AgentsPage } from './pages/AgentsPage';
import { AgentChatPage } from './pages/AgentChatPage';
import { IssuesPage } from './pages/IssuesPage';
import { ReviewsPage } from './pages/ReviewsPage';
import { PulsePage } from './pages/PulsePage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
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
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'issues', element: <IssuesPage /> },
      { path: 'projects', element: <ProjectsPage /> },
      { path: 'projects/new', element: <ProjectWizardPage /> },
      { path: 'projects/:slug', element: <ProjectDetailPage /> },
      { path: 'projects/:slug/deliverables', element: <ProjectDeliverablesPage /> },
      { path: 'reviews', element: <ReviewsPage /> },
      { path: 'pulse', element: <PulsePage /> },
      { path: 'teams/:teamId/members', element: <TeamMembersPage /> },
      { path: 'teams/:teamId/agents', element: <AgentsPage /> },
      { path: 'teams/:teamId/agents/:agentId/chat', element: <AgentChatPage /> },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]);
