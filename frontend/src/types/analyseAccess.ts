/** Accès à une analyse (`/api/analyses/{id}/access`). Les règles sont tenues par le serveur. */
import type { Version } from "@/types/analyse";

export interface AccessPerson {
  /** Absent pour une personne pas encore enregistrée. */
  id?: string;
  userId?: string;
  name: string;
  email: string;
  roleId: string;
  pending: boolean;
  editable: boolean;
}

export interface AnalyseAccess {
  canEdit: boolean;
  groups: { id: string; name: string; editable: boolean }[];
  availableGroups: { id: string; name: string }[];
  people: AccessPerson[];
  assignableRoleIds: string[];
  versions: Version<{ groups: string[]; people: string[] }>[];
}

export const describeAccess = ({ groups, people }: { groups: string[]; people: string[] }) =>
  `Groupes : ${groups.join(", ") || "aucun"} · Personnes : ${people.join(", ") || "aucune"}`;
