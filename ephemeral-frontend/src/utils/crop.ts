import type { Box } from "@/types";

/**
 * Zone de la page à montrer pour un ensemble de rectangles : leur union agrandie d'une marge, jamais plus petite qu'un
 * minimum (un seul mot resterait illisible, perdu dans une image minuscule), et toujours contenue dans la page (la
 * fenêtre se décale plutôt que de déborder). Coordonnées normalisées, comme les rectangles.
 */
export function cropRegion(boxes: Box[], { marginX = 0.05, marginY = 0.035, minWidth = 0.4, minHeight = 0.14 } = {}): Box {
  const x0 = Math.min(...boxes.map((b) => b.x_min)) - marginX;
  const y0 = Math.min(...boxes.map((b) => b.y_min)) - marginY;
  const x1 = Math.max(...boxes.map((b) => b.x_max)) + marginX;
  const y1 = Math.max(...boxes.map((b) => b.y_max)) + marginY;

  const fit = (low: number, high: number, minSize: number): [number, number] => {
    const size = Math.min(1, Math.max(high - low, minSize));
    const start = Math.min(Math.max((low + high) / 2 - size / 2, 0), 1 - size);
    return [start, start + size];
  };
  const [xMin, xMax] = fit(x0, x1, minWidth);
  const [yMin, yMax] = fit(y0, y1, minHeight);
  return { x_min: xMin, y_min: yMin, x_max: xMax, y_max: yMax };
}
