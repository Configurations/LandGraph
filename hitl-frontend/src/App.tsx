import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { MobileNav } from './components/layout/MobileNav';
import { ToastContainer } from './components/ui/Toast';
import { useWebSocket } from './hooks/useWebSocket';
import { useTeamStore } from './stores/teamStore';
import { useAuthStore } from './stores/authStore';

export function App(): JSX.Element {
  const activeTeamId = useTeamStore((s) => s.activeTeamId);
  const loadTeams = useTeamStore((s) => s.loadTeams);
  const loadUser = useAuthStore((s) => s.loadUser);

  useWebSocket(activeTeamId);

  useEffect(() => {
    void loadUser();
    void loadTeams();
  }, [loadUser, loadTeams]);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar className="hidden sm:flex" />
      <div className="flex flex-1 flex-col min-w-0">
        <Header titleKey="nav.inbox" />
        <main className="flex-1 overflow-y-auto pb-16 sm:pb-0">
          <Outlet />
        </main>
      </div>
      <MobileNav className="sm:hidden" />
      <ToastContainer />
    </div>
  );
}
