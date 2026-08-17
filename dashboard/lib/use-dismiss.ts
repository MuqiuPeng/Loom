"use client";

import { useEffect, type RefObject } from "react";

/** Close a panel when the user clicks anywhere outside it.
 *
 * Listens on mousedown rather than click so the panel is already closing by
 * the time a click lands on a row underneath — that way clicking straight
 * from one row to another selects the new one instead of needing two clicks.
 *
 * No backdrop element: a backdrop would swallow that first click.
 */
export function useDismissOnOutsideClick(
  ref: RefObject<HTMLElement | null>,
  onDismiss: () => void,
  enabled: boolean
) {
  useEffect(() => {
    if (!enabled) return;

    const onMouseDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target || !ref.current) return;
      // Ignore clicks on nodes already detached from the document — a row
      // removed by its own delete button would otherwise read as "outside".
      if (!target.isConnected) return;
      if (ref.current.contains(target)) return;
      onDismiss();
    };

    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, [ref, onDismiss, enabled]);
}
