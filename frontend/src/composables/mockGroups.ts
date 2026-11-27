/** Maquette (#657) : personnes, rôles et groupes fictifs. */
import { PERMISSION_LABELS, type Group, type Person, type Persona, type Role } from "@/types/groups";

export const GROUP_ADMIN_ROLE = "group-admin";

export const MOCK_PEOPLE: Person[] = [
  { name: "Camille Durand", email: "camille.durand@example.org" },
  { name: "Sacha Petit", email: "sacha.petit@example.org" },
  { name: "Noa Lambert", email: "noa.lambert@example.org" },
  { name: "Alix Moreau", email: "alix.moreau@example.org" },
  { name: "Charlie Roux", email: "charlie.roux@example.org" },
];

export const MOCK_PERSONAS: Persona[] = [
  { id: "super", label: "Super admin", email: "super.admin@example.org", superAdmin: true },
  { id: "admin", label: "Camille Durand, admin de « Service culture »", email: "camille.durand@example.org", superAdmin: false },
  { id: "member", label: "Sacha Petit, instructeur", email: "sacha.petit@example.org", superAdmin: false },
];

const role = (id: string, name: string, description: string, permissions: string[], system = false): Role => ({
  id,
  name,
  description,
  permissions,
  system,
  versions: [],
});

export const mockRoles = (): Role[] => [
  role(GROUP_ADMIN_ROLE, "Admin de groupe", "Toutes les permissions sur son groupe.", Object.keys(PERMISSION_LABELS), true),
  role("instructor", "Instructeur", "Instruit les dossiers.", [
    "dossier.view",
    "dossier.edit",
    "dossier.run",
    "dossier.validate",
    "dossier.generate",
  ]),
  role("reader", "Lecteur", "Consulte sans modifier.", ["dossier.view"]),
];

const member = (index: number, roleId: string) => ({ ...MOCK_PEOPLE[index], roleId });

const group = (id: string, name: string, description: string, members: Group["members"]): Group => ({
  id,
  name,
  description,
  members,
  versions: [],
  journal: [],
});

export const mockGroups = (): Group[] => [
  group("culture", "Service culture", "Instruction des demandes culturelles.", [
    member(0, GROUP_ADMIN_ROLE),
    member(1, "instructor"),
    member(2, "reader"),
    { name: "", email: "futur.agent@example.org", roleId: "instructor" },
  ]),
  group("road", "Sécurité routière", "Suivi des permis et des immatriculations.", [
    member(3, GROUP_ADMIN_ROLE),
    member(4, "instructor"),
  ]),
  group("archive", "Archives", "Groupe vide, pour essayer la suppression.", []),
];
