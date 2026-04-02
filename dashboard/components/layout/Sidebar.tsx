"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const MAIN_NAV = [
  {
    section: "Resume Tailor",
    items: [
      { label: "Profile", href: "/resume-tailor/profile" },
      { label: "Resumes", href: "/resume-tailor/resumes" },
      { label: "Jobs", href: "/resume-tailor/jobs" },
      { label: "Workflows", href: "/resume-tailor/workflows" },
    ],
  },
  {
    section: "System",
    items: [
      { label: "Logs", href: "/logs" },
    ],
  },
];

const EXPO_NAV = [
  {
    section: "Expo",
    items: [
      { label: "Resume Tailor", href: "/expo/resume-tailor/profile" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  if (pathname === "/login" || pathname.startsWith("/expo")) return null;

  const isExpo = pathname.startsWith("/expo");
  const navItems = isExpo ? EXPO_NAV : MAIN_NAV;

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setOpen(true)}
        className="fixed top-4 left-4 z-40 md:hidden p-2 rounded-md bg-white border border-gray-200 shadow-sm"
        aria-label="Open menu"
      >
        <svg className="h-5 w-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/30 z-40 md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed left-0 top-0 h-screen w-60 bg-white border-r border-gray-200 flex flex-col z-50
          transition-transform duration-200 ease-in-out
          ${open ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
        <div className="px-5 py-5 border-b border-gray-100 flex items-center justify-between">
          <Link href={isExpo ? "/expo/resume-tailor/profile" : "/"} className="text-xl font-bold tracking-tight">
            <span className="text-indigo-600">Loom</span>
          </Link>
          <button
            onClick={() => setOpen(false)}
            className="md:hidden p-1 rounded text-gray-400 hover:text-gray-600"
            aria-label="Close menu"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {navItems.map((section) => (
            <div key={section.section} className="mb-6">
              <h3 className="px-2 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {section.section}
              </h3>
              <ul className="space-y-0.5">
                {section.items.map((item) => {
                  const active = pathname === item.href || pathname.startsWith(item.href + "/");
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={`block px-3 py-2 rounded-md text-sm transition-colors ${
                          active
                            ? "bg-indigo-50 text-indigo-700 font-medium"
                            : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="px-5 py-3 border-t border-gray-100 text-xs text-gray-400">
          v0.1.0
        </div>
      </aside>
    </>
  );
}
