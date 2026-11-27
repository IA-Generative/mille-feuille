/** Place les groupes d'un thème de ressemblance : un amas par groupe, ce qui est partagé au centre. */
import type { Resemblance } from "@/types/crossSearch";

export interface ClusterNode {
  id: string;
  groupId: string;
  /** Absent pour le centre du groupe (ce qui est partagé). */
  dossierId?: string;
  x: number;
  y: number;
}

export interface Cluster {
  groupId: string;
  x: number;
  y: number;
  radius: number;
}

export interface ClusterLayout {
  nodes: ClusterNode[];
  edges: { source: string; target: string }[];
  clusters: Cluster[];
}

/** Distance entre le centre d'un groupe et ses dossiers, et rayon réservé à son amas. */
const SPOKE = 1;
const RADIUS = 2.1;

export function layoutClusters(groups: Resemblance[]): ClusterLayout {
  // Le cadre est plus large que haut : un peu plus de colonnes que de lignes.
  const columns = Math.max(1, Math.ceil(Math.sqrt(groups.length * 1.6)));
  const cell = 2.2 * RADIUS;

  const layout: ClusterLayout = { nodes: [], edges: [], clusters: [] };
  groups.forEach((group, index) => {
    // En grille, de gauche à droite puis de haut en bas (l'axe y de sigma monte).
    const center = { x: (index % columns) * cell, y: -Math.floor(index / columns) * cell };
    layout.clusters.push({ groupId: group.id, ...center, radius: RADIUS });
    layout.nodes.push({ id: `${group.id}:hub`, groupId: group.id, ...center });

    group.dossierIds.forEach((dossierId, position) => {
      // Un dossier présent dans plusieurs groupes a un nœud dans chacun : les amas restent séparés. Les rayons sont en
      // diagonale pour que les libellés ne se croisent pas.
      const angle = (2 * Math.PI * position) / group.dossierIds.length + Math.PI / group.dossierIds.length - Math.PI / 2;
      const id = `${group.id}:${dossierId}`;
      layout.nodes.push({
        id,
        groupId: group.id,
        dossierId,
        x: center.x + SPOKE * Math.cos(angle),
        y: center.y + SPOKE * Math.sin(angle),
      });
      layout.edges.push({ source: `${group.id}:hub`, target: id });
    });
  });
  return layout;
}
