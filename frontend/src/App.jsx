import { useState, useEffect } from 'react';
import { getProfile } from './api.js';
import ProfilePage from './pages/ProfilePage.jsx';
import ResumePage from './pages/ResumePage.jsx';
import FillPage from './pages/FillPage.jsx';
import LogsPage from './pages/LogsPage.jsx';
import ApplicationsPage from './pages/ApplicationsPage.jsx';

const NAV_ITEMS = [
  {
    id: 'profile',
    label: 'Profile',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
      </svg>
    ),
  },
  {
    id: 'resume',
    label: 'Documents',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    id: 'fill',
    label: 'Fill a Form',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    ),
  },
  {
    id: 'applications',
    label: 'Applications',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    id: 'logs',
    label: 'Logs',
    icon: (
      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
      </svg>
    ),
  },
];

export default function App() {
  const [activePage, setActivePage] = useState('profile');
  const [userName, setUserName] = useState('');

  useEffect(() => {
    getProfile()
      .then((p) => {
        if (p.firstName || p.lastName) {
          setUserName(`${p.firstName} ${p.lastName}`.trim());
        }
      })
      .catch(() => {
        // Silently ignore — backend may not be running yet
      });
  }, []);

  const pages = {
    profile: <ProfilePage onProfileSaved={(name) => setUserName(name)} />,
    resume: <ResumePage />,
    fill: <FillPage />,
    applications: <ApplicationsPage />,
    logs: <LogsPage />,
  };

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 bg-slate-900 flex flex-col flex-shrink-0 overflow-y-auto">
        {/* Logo */}
        <div className="px-6 pt-8 pb-6 border-b border-slate-700">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 bg-indigo-500 rounded-lg flex items-center justify-center flex-shrink-0">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-white font-semibold text-lg tracking-tight">JobAutomata</span>
          </div>
          <p className="text-slate-400 text-xs leading-snug mt-1">
            Fill forms. You submit.
          </p>
        </div>

        {/* User name (if set) */}
        {userName && (
          <div className="px-6 py-3 border-b border-slate-800">
            <p className="text-slate-300 text-sm font-medium truncate">{userName}</p>
            <p className="text-slate-500 text-xs">Active profile</p>
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActivePage(item.id)}
                className={[
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left',
                  isActive
                    ? 'bg-slate-700 text-white border-l-2 border-indigo-400 pl-[10px]'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800',
                ].join(' ')}
              >
                {item.icon}
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800">
          <p className="text-slate-600 text-xs">v0.1.0 · MIT License</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-8 max-w-3xl">
          {pages[activePage]}
        </div>
      </main>
    </div>
  );
}
