/**
 * Source d'un fichier déposé dans un dossier (courrier, guichet, autre administration…). Libre, définie par
 * l'utilisateur. Rattachée à une analyse (catalogue de l'analyse, proposée pour tous ses dossiers), ou « tampon » :
 * créée depuis un dossier « à ranger », visible dans ce seul dossier jusqu'à son rattachement à une analyse.
 */
export interface DocumentSource {
  id: string;
  name: string;
  description: string;
  analyseId?: string;
  /** Renseigné pour une source tampon seulement. */
  dossierId?: string;
}

/** Ce que l'utilisateur a choisi au moment d'un dépôt ; une nouvelle source n'est créée qu'à l'envoi. */
export type SourceChoice =
  | { kind: "none" }
  | { kind: "existing"; id: string }
  | { kind: "new"; name: string; description: string };

export const NO_SOURCE: SourceChoice = { kind: "none" };
