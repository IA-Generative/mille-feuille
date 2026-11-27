/** L'apparence commune des graphes sigma.js : formes, pictogrammes, liens courbes et libellés. */
import { layerBorder } from "@sigma/node-border";
import { layerImage } from "@sigma/node-image";
import type Graph from "graphology";
import Sigma, { DEFAULT_STYLES } from "sigma";
import { layerFill, pathCurved, sdfCircle, sdfSquare } from "sigma/rendering";

import type { readPalette } from "@/components/crossSearch/graphTheme";

/** Nœuds attendus : `shape` (circle ou square), `image`, `iconColor`, `color`, `size`, `label`. */
export function createRenderer(graph: Graph, element: HTMLElement, palette: ReturnType<typeof readPalette>) {
  return new Sigma(graph, element, {
    primitives: {
      // « clusters » : le fond des amas, sous les liens et les nœuds.
      depthLayers: ["clusters", "edges", "topEdges", "nodes", "topNodes"],
      nodes: {
        shapes: [sdfCircle(), sdfSquare({ cornerRadius: 0.35 })],
        // Les attributs lus par les couches doivent être déclarés, puis reliés dans les styles.
        variables: { image: { type: "string", default: "" }, iconColor: { type: "color", default: "#ffffff" } },
        // Fond coloré, pictogramme blanc, puis un liseré de la couleur de la page qui détache le nœud.
        layers: [
          layerFill({ color: { attribute: "color" } }),
          layerImage({ drawingMode: "color", colorAttribute: "iconColor", imageAttribute: "image", padding: 0.28 }),
          layerBorder({
            borders: [
              { size: 2.5, color: palette.background, mode: "pixels" },
              { size: 0, color: "#00000000", fill: true },
            ],
          }),
        ],
        label: { font: { family: "Marianne, arial, sans-serif" }, margin: 4 },
      },
      edges: { paths: [pathCurved()], variables: { curvature: { type: "number", default: 0.16 } } },
    },
    styles: {
      nodes: [
        DEFAULT_STYLES.nodes,
        {
          shape: { attribute: "shape" },
          image: { attribute: "image" },
          iconColor: { attribute: "iconColor" },
          size: { attribute: "size" },
          labelColor: palette.text,
          labelSize: 12,
          labelPosition: "below",
          labelBackgroundColor: palette.background,
          labelBackgroundPadding: 3,
          backdropColor: palette.background,
          backdropBorderColor: palette.border,
          backdropBorderWidth: 1,
          backdropCornerRadius: 8,
        },
      ],
      edges: [DEFAULT_STYLES.edges, { path: "curved", curvature: 0.16 }],
    },
    // Tailles en pixels : sinon les nœuds grossissent avec l'échelle des positions.
    settings: {
      itemSizesReference: "screen",
      stagePadding: 70,
      labelRenderedSizeThreshold: 0,
      labelDensity: 3,
      enableEdgeEvents: true,
      edgePickingPadding: 6,
    },
  }) as unknown as Sigma;
}
