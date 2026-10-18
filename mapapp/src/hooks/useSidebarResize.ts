import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

function widthLimits() {
  const available = window.innerWidth - (window.innerWidth <= 600 ? 48 : 240);
  const max = Math.max(240, Math.min(720, available));
  return { min: Math.min(360, max), max };
}

export function useSidebarResize() {
  const [limits, setLimits] = useState(widthLimits);
  const [preferredWidth, setPreferredWidth] = useState(420);
  const [resizing, setResizing] = useState(false);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const width = Math.min(limits.max, Math.max(limits.min, preferredWidth));
  const updateWidth = (next: number) => setPreferredWidth(Math.min(limits.max, Math.max(limits.min, next)));

  useEffect(() => {
    const onResize = () => setLimits(widthLimits());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!resizing) return;
    const { cursor, userSelect } = document.body.style;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = cursor;
      document.body.style.userSelect = userSelect;
    };
  }, [resizing]);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.focus();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, width };
    setResizing(true);
  }
  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    if (drag.current) updateWidth(drag.current.width + drag.current.x - event.clientX);
  }
  function stopResize() {
    drag.current = null;
    setResizing(false);
  }
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 48 : 16;
    const next = { ArrowLeft: width + step, ArrowRight: width - step, Home: limits.min, End: limits.max }[event.key];
    if (next !== undefined) {
      event.preventDefault();
      updateWidth(next);
    }
  }
  return {
    width, limits, resizing,
    handleProps: { onPointerDown, onPointerMove, onPointerUp: stopResize, onPointerCancel: stopResize, onLostPointerCapture: stopResize, onKeyDown },
  };
}
