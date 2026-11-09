import { useLayoutEffect } from "react";

/**
 * Marks each `[data-reveal]` block with `data-in` the first time it scrolls into view, so its `.reveal` items rise
 * one by one, once (motion guideline: a list staggers only when it first appears).
 *
 * Items wait out of sight only while `data-reveal-on` is on <html>, which this sets before the first paint and
 * removes on unmount; so if it never runs, when motion is reduced, or when printing, everything is simply there.
 * Blocks already in view when the page opens get `data-in="load"`, so they can wait for the hero above them.
 */
export function useReveal(): void {
  useLayoutEffect(() => {
    const root = document.documentElement;
    const blocks = [...document.querySelectorAll<HTMLElement>("[data-reveal]:not([data-in])")];
    const opened = performance.now();
    const show = (el: Element) => el.setAttribute("data-in", performance.now() - opened < 500 ? "load" : "");
    if (!("IntersectionObserver" in window)) {
      blocks.forEach(show);
      return;
    }
    root.setAttribute("data-reveal-on", "");
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          show(e.target);
          io.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -15% 0px" },
    );
    blocks.forEach((b) => io.observe(b));
    return () => {
      io.disconnect();
      root.removeAttribute("data-reveal-on");
    };
  }, []);
}
