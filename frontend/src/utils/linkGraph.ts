/** Le graphe affiché, sans rien de l'affichage : dossiers, points communs et dossiers non accessibles. */
import {
  DOSSIER_COLOR,
  HIDDEN_COLOR,
  RELATED_COLOR,
  SHARED_KINDS,
  type CrossSearchResult,
  type Selection,
  type SharedKind,
} from "@/types/crossSearch";

export interface GraphNode {
  id: string;
  type: "dossier" | "item" | "hidden";
  /** Pour un point commun : sa nature. */
  kind?: SharedKind;
  label: string;
  color: string;
  size: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface LinkGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const edgeId = (source: string, target: string) => `${source}--${target}`;

export const hiddenNodeId = (themeName: string | null) => `hidden:${themeName ?? ""}`;

export const hiddenLabel = (count: number, themeName: string | null) =>
  `${count} dossier${count > 1 ? "s" : ""} non accessible${count > 1 ? "s" : ""} · ${themeName ?? "Sans thème"}`;

export function buildLinkGraph(result: CrossSearchResult, kinds: SharedKind[]): LinkGraphData {
  const items = result.items.filter((item) => kinds.includes(item.kind));
  const color = (kind: SharedKind) => SHARED_KINDS.find((k) => k.value === kind)!.color;

  const nodes: GraphNode[] = [
    ...result.dossiers.map((d) => {
      // Avec une sélection de départ, les autres dossiers sont plus petits et plus pâles.
      const isRelated = result.anchorIds.length > 0 && !result.anchorIds.includes(d.id);
      return {
        id: d.id,
        type: "dossier" as const,
        label: d.name,
        color: isRelated ? RELATED_COLOR : DOSSIER_COLOR,
        size: isRelated ? 15 : 21,
      };
    }),
    ...items.map((item) => ({
      id: item.id,
      type: "item" as const,
      kind: item.kind,
      label: item.label,
      color: color(item.kind),
      size: 11 + item.dossierIds.length,
    })),
    ...result.hidden.map((link) => ({
      id: hiddenNodeId(link.themeName),
      type: "hidden" as const,
      label: `${link.count} non accessibles`,
      color: HIDDEN_COLOR,
      size: 14,
    })),
  ];
  const edges: GraphEdge[] = [
    ...items.flatMap((item) => item.dossierIds.map((id) => ({ source: id, target: item.id }))),
    ...result.hidden.flatMap((link) =>
      link.dossierIds.map((id) => ({ source: id, target: hiddenNodeId(link.themeName) })),
    ),
  ];

  return { nodes, edges };
}

/** Les dossiers qui partagent au moins un point commun avec `dossierId`, les plus liés d'abord. */
export function relatedDossiers(result: CrossSearchResult, dossierId: string) {
  return result.dossiers
    .filter((dossier) => dossier.id !== dossierId)
    .map((dossier) => ({ dossier, items: sharedItems(result, dossierId, dossier.id) }))
    .filter(({ items }) => items.length)
    .sort((a, b) => b.items.length - a.items.length);
}

/**
 * Ce qui reste avec les seuls types de liens cochés. Un dossier amené par un lien décoché disparaît ; les dossiers
 * choisis et les résultats d'une recherche restent.
 */
export function restrictToKinds(result: CrossSearchResult, kinds: SharedKind[]): CrossSearchResult {
  const items = result.items.filter((item) => kinds.includes(item.kind));
  const linked = new Set(items.flatMap((item) => item.dossierIds));
  const keeps = (id: string) => !result.anchorIds.length || result.anchorIds.includes(id) || linked.has(id);
  return { ...result, items, dossiers: result.dossiers.filter((d) => keeps(d.id)) };
}

export function sharedItems(result: CrossSearchResult, first: string, second: string) {
  return result.items.filter((item) => item.dossierIds.includes(first) && item.dossierIds.includes(second));
}

/** Ce que le graphe met en avant pour une sélection : `null` si elle ne désigne rien de dessiné. */
export function highlightOf(data: LinkGraphData, selection: Selection | null) {
  if (!selection) return null;
  const touches = (edge: GraphEdge, id: string) => edge.source === id || edge.target === id;
  let edges: GraphEdge[];

  if (selection.type === "node") {
    edges = data.edges.filter((edge) => touches(edge, selection.id));
  } else if (selection.type === "link") {
    edges = data.edges.filter((edge) => edge.source === selection.dossierId && edge.target === selection.targetId);
  } else {
    // Les chemins « dossier — point commun — dossier » entre les deux.
    const [first, second] = selection.dossierIds;
    const targets = (id: string) => data.edges.filter((e) => e.source === id).map((e) => e.target);
    const common = new Set(targets(first).filter((target) => targets(second).includes(target)));
    edges = data.edges.filter((e) => common.has(e.target) && selection.dossierIds.includes(e.source));
  }

  const nodes = new Set(edges.flatMap((edge) => [edge.source, edge.target]));
  if (selection.type === "node") nodes.add(selection.id);
  if (![...nodes].some((id) => data.nodes.some((node) => node.id === id))) return null;
  return { nodes, edges: new Set(edges.map((e) => edgeId(e.source, e.target))) };
}
