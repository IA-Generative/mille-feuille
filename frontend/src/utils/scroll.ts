/**
 * Amène un élément dans la zone visible en défilant le moins possible. Sans animation si la personne a demandé de
 * réduire les animations (prefers-reduced-motion).
 */
export function scrollIntoViewSoft(element: Element | null | undefined) {
  if (!element) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
}
