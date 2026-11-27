// Maquette des accès à une analyse (#662) : données fictives.
import type { Version } from "@/types/analyse";

export interface MockPerson {
  email: string;
  name: string;
}

export interface MockAssignment extends MockPerson {
  roleId: string;
}

export interface MockRole {
  id: string;
  name: string;
}

export interface MockGroup {
  id: string;
  name: string;
  members: MockAssignment[];
}

export interface AccessContent {
  groupIds: string[];
  people: MockAssignment[];
}

export interface AnalyseAccess extends AccessContent {
  versions: Version<AccessContent>[];
}

export interface Persona {
  id: string;
  label: string;
  email: string;
  superAdmin: boolean;
}
