import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <div className="flex min-h-screen print:block">
      <div className="print:hidden">
        <Sidebar />
      </div>
      <main className="ml-60 flex-1 p-8 max-w-full overflow-auto print:ml-0 print:p-0">
        <Outlet />
      </main>
    </div>
  );
}
