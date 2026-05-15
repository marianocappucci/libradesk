import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="ml-60 flex-1 p-8 max-w-full overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
