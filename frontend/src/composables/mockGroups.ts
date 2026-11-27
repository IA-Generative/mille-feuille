/** Maquette des accès à une analyse (#662) : personnes, rôles et groupes fictifs. */
import type { MockAssignment, MockGroup, MockPerson, MockRole, Persona } from "@/types/mockAccess";

export const GROUP_ADMIN_ROLE = "group-admin";

export const MOCK_PEOPLE: MockPerson[] = [
  { name: "Camille Durand", email: "camille.durand@example.org" },
  { name: "Sacha Petit", email: "sacha.petit@example.org" },
  { name: "Noa Lambert", email: "noa.lambert@example.org" },
  { name: "Alix Moreau", email: "alix.moreau@example.org" },
];

export const MOCK_PERSONAS: Persona[] = [
  { id: "super", label: "Super admin", email: "super.admin@example.org", superAdmin: true },
  { id: "admin", label: "Camille Durand, admin de « Service culture »", email: "camille.durand@example.org", superAdmin: false },
  { id: "member", label: "Sacha Petit, instructeur", email: "sacha.petit@example.org", superAdmin: false },
];

export const mockRoles = (): MockRole[] => [
  { id: GROUP_ADMIN_ROLE, name: "Admin de groupe" },
  { id: "instructor", name: "Instructeur" },
  { id: "reader", name: "Lecteur" },
];

const member = (index: number, roleId: string): MockAssignment => ({ ...MOCK_PEOPLE[index], roleId });

export const mockGroups = (): MockGroup[] => [
  { id: "culture", name: "Service culture", members: [member(0, GROUP_ADMIN_ROLE), member(1, "instructor")] },
  { id: "road", name: "Sécurité routière", members: [member(3, GROUP_ADMIN_ROLE)] },
];
