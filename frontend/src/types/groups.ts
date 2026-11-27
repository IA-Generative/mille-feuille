// Groupes et rôles de l'application (épique #656). Maquette (#657) : aucun appel au backend.
import type { Version } from "@/types/analyse";

/** Liste fixe des permissions : un rôle en est un sous-ensemble. */
export const PERMISSION_FAMILIES = [
  {
    title: "Dossiers",
    permissions: {
      "dossier.view": "Voir un dossier",
      "dossier.edit": "Modifier un dossier",
      "dossier.run": "Lancer une analyse sur un dossier",
      "dossier.validate": "Valider",
      "dossier.generate": "Générer un document",
      "dossier.delete": "Supprimer un dossier",
    },
  },
  {
    title: "Analyses",
    permissions: {
      "analyse.create": "Créer une analyse",
      "analyse.configure": "Configurer une analyse",
      "analyse.access": "Gérer les accès à une analyse",
    },
  },
  { title: "Groupe", permissions: { "group.members": "Gérer les membres" } },
] as const;

export type Permission = keyof (typeof PERMISSION_FAMILIES)[number]["permissions"] | (string & {});

export const PERMISSION_LABELS: Record<string, string> = Object.assign(
  {},
  ...PERMISSION_FAMILIES.map((family) => family.permissions),
);

export interface RoleContent {
  name: string;
  description: string;
  permissions: Permission[];
}

export interface Role extends RoleContent {
  id: string;
  /** Rôle fourni et figé : ni modifiable ni supprimable. */
  system: boolean;
  versions: Version<RoleContent>[];
}

export interface Person {
  email: string;
  /** Vide tant que la personne ne s'est jamais connectée. */
  name: string;
}

/** Une personne et son rôle, dans un groupe ou sur une analyse. */
export interface Assignment extends Person {
  roleId: string;
}

export interface JournalEntry {
  id: string;
  at: string;
  author: string;
  text: string;
}

export interface GroupContent {
  name: string;
  description: string;
}

export interface Group extends GroupContent {
  id: string;
  members: Assignment[];
  versions: Version<GroupContent>[];
  journal: JournalEntry[];
}

export interface AccessContent {
  groupIds: string[];
  people: Assignment[];
}

export interface AnalyseAccess extends AccessContent {
  versions: Version<AccessContent>[];
}

/** Maquette : la personne dont on prend le point de vue. */
export interface Persona {
  id: string;
  label: string;
  email: string;
  superAdmin: boolean;
}
