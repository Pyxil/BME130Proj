import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { USE_MOCKS } from "../services/api";

const links = [
  { to: "/practice", label: "Practice" },
  { to: "/dashboard", label: "Dashboard" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Settings" },
  { to: "/about", label: "How it works" },
];

export function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2">
        Skip to main content
      </a>
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <NavLink to="/practice" className="flex items-center gap-2 text-xl font-bold text-brand-800 dark:text-brand-200">
            <span aria-hidden="true" className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-700 text-white">🎙</span>
            SayItRight
          </NavLink>
          {USE_MOCKS && <span className="rounded-full bg-amber-200 px-3 py-1 text-sm font-bold text-amber-950">Mock data</span>}
          {user && (
            <nav aria-label="Main" className="-mx-1 flex items-center gap-1 overflow-x-auto whitespace-nowrap pb-1 sm:mx-0 sm:pb-0">
              {links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  className={({ isActive }) =>
                    `rounded-lg px-3 py-2 font-bold ${isActive ? "bg-brand-100 text-brand-900 dark:bg-brand-900 dark:text-brand-50" : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`
                  }
                >
                  {l.label}
                </NavLink>
              ))}
              <button
                type="button"
                onClick={() => { logout(); navigate("/login"); }}
                className="rounded-lg px-3 py-2 font-bold text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              >
                Sign out
              </button>
            </nav>
          )}
        </div>
      </header>
      <main id="main" className="mx-auto max-w-5xl px-4 py-6 sm:py-10">{children}</main>
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-sm text-slate-500 dark:text-slate-400">
        Practice tool only: scores are automated estimates, not a clinical assessment or diagnosis.
      </footer>
    </div>
  );
}
