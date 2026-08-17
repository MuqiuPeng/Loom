"use client";

import { useEffect, useState } from "react";

/** A one-bit shared signal: is the app nav collapsed?
 *
 * The Sidebar lives in the root layout and the pages that want the room live
 * far below it, so neither can pass the other a prop. This is deliberately a
 * module-level store rather than a Context — a Provider would have to wrap the
 * whole layout to carry a single boolean.
 */
let collapsed = false;
const listeners = new Set<(value: boolean) => void>();

export function setNavCollapsed(value: boolean) {
  if (collapsed === value) return;
  collapsed = value;
  listeners.forEach((notify) => notify(value));
}

export function useNavCollapsed(): boolean {
  const [value, setValue] = useState(collapsed);
  useEffect(() => {
    listeners.add(setValue);
    setValue(collapsed);
    return () => {
      listeners.delete(setValue);
    };
  }, []);
  return value;
}

/** Collapse while `active`, and always restore on unmount — otherwise
 * navigating away from a page with a panel open leaves the nav hidden. */
export function useCollapseNavWhile(active: boolean) {
  useEffect(() => {
    setNavCollapsed(active);
    return () => setNavCollapsed(false);
  }, [active]);
}
