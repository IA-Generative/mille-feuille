// Accès aux dossiers par groupe (issue #177). L'accès d'un dossier se lit et se modifie par l'API
// (`/api/dossiers/{id}/access`, `/api/dossiers/bulk-access`) : la règle est appliquée par le serveur.

/** « restricted » : seuls les groupes associés (et les administrateurs). « analyse » : tout utilisateur ayant accès à l'analyse. */
export type Visibility = "restricted" | "analyse";

export const VISIBILITY_LABELS: Record<Visibility, string> = {
  restricted: "Restreint",
  analyse: "Selon l'analyse",
};

export const VISIBILITY_HINTS: Record<Visibility, string> = {
  restricted: "Seuls les membres des groupes choisis (et les administrateurs) voient ce dossier.",
  analyse: "Toute personne ayant accès à l'analyse voit ce dossier.",
};

/** Ce qu'on envoie pour changer l'accès : la visibilité et les groupes (qui **remplacent** les groupes actuels). */
export interface DossierAccess {
  visibility: Visibility;
  /** Chemins de groupes Keycloak, comparés tels quels (pas d'héritage entre groupes). */
  groups: string[];
}

export interface AccessGroup {
  path: string;
  /** Identifiant de la personne qui a associé le groupe. */
  grantedBy: string | null;
  grantedAt: string;
}

/** Accès d'un dossier tel que le serveur le décrit. */
export interface DossierAccessState extends DossierAccess {
  details: AccessGroup[];
  /** Seuls les administrateurs modifient l'accès. */
  canEdit: boolean;
  /** Groupes que la personne connectée peut associer : les siens (pas d'héritage). */
  availableGroups: string[];
}

/** Effet d'un changement sur la personne affectée (simulation ou résultat). */
export interface AccessImpact {
  /** La personne affectée perd (ou a perdu) l'accès, et son affectation est (ou a été) annulée. */
  assigneeUnassigned: boolean;
  unassignedPerson: { id: string; name: string } | null;
}

export interface BulkAccessResult {
  updated: number;
  unchanged: number;
  unassigned: number;
}

/** « /service-culture » → « Service culture » (le chemin exact est affiché à côté). */
export function groupLabel(path: string): string {
  const name = path.replace(/^\//, "").replace(/[-_]/g, " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
}
