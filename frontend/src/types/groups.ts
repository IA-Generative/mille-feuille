// Groupes, rôles et membres de l'application (`/api/groups`, `/api/roles`). Les règles sont tenues par le serveur.
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

export const PERMISSION_LABELS: Record<string, string> = Object.assign(
  {},
  ...PERMISSION_FAMILIES.map((family) => family.permissions),
);

/** Ancienne valeur d'un champ, restaurable. */
export type FieldVersion = Version<{ field: string; value: string | string[] }>;

export interface Group {
  id: string;
  name: string;
  description: string;
  memberCount: number;
  canManageMembers: boolean;
  deletable: boolean;
  versions: FieldVersion[];
}

export interface Role {
  id: string;
  name: string;
  description: string;
  permissions: string[];
  /** Fourni par l'application : figé. */
  system: boolean;
  inUse: boolean;
  /** La personne connectée peut l'attribuer dans le groupe demandé. */
  assignable: boolean;
  versions: FieldVersion[];
}

export interface Member {
  id: string;
  name: string;
  email: string;
  roleId: string;
  /** Pas encore rattachée à un compte. */
  pending: boolean;
  editable: boolean;
}

export interface GroupEvent {
  id: string;
  type: string;
  createdAt: string;
  actorName: string | null;
  subject: string | null;
  roleName: string | null;
  previousRoleName: string | null;
}

const FIELD_LABELS: Record<string, string> = { name: "Nom", description: "Description", permissions: "Permissions" };

export function describeVersion({ field, value }: { field: string; value: string | string[] }): string {
  const text = Array.isArray(value) ? value.map((p) => PERMISSION_LABELS[p] ?? p).join(", ") : value;
  return `${FIELD_LABELS[field] ?? field} : ${text || "(vide)"}`;
}

export function describeEvent(event: GroupEvent): string {
  const who = event.subject ?? "une personne";
  const text =
    {
      group_created: "Groupe créé",
      group_updated: "Groupe modifié",
      group_deleted: "Groupe supprimé",
      member_added: `${who} ajouté au groupe : ${event.roleName}`,
      member_role_changed: `${who} : ${event.previousRoleName} → ${event.roleName}`,
      member_removed: `${who} retiré du groupe`,
    }[event.type] ?? event.type;
  return event.actorName ? `${event.actorName} · ${text}` : text;
}
