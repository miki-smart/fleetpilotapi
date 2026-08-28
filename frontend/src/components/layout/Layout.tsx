import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu, Truck } from 'lucide-react';
import { Sidebar } from './Sidebar';

export function Layout() {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar open={open} onClose={() => setOpen(false)} />

      <div className="flex-1 min-w-0 lg:ml-60 min-h-screen flex flex-col">
        {/* Mobile top bar */}
        <header className="lg:hidden sticky top-0 z-30 flex items-center gap-3 px-4 py-3 bg-slate-900 text-white">
          <button
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
            className="p-1.5 rounded-md hover:bg-slate-800"
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-sm">FleetPilot</span>
        </header>

        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
