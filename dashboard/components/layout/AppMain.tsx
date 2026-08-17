"use client";

import { useNavCollapsed } from "@/lib/nav-collapse";

/** The content area, which has to reclaim the nav's gutter when the nav
 * collapses — otherwise a detail panel opens into a 240px dead strip. */
export default function AppMain({ children }: { children: React.ReactNode }) {
  const collapsed = useNavCollapsed();
  return (
    <main
      className={`min-h-screen p-4 pt-16 md:p-8 md:pt-8 transition-[margin] duration-200 ease-in-out ${
        collapsed ? "md:ml-0" : "md:ml-60"
      }`}
    >
      {children}
    </main>
  );
}
