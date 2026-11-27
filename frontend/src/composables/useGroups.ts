/** Maquette (#657) : l'état et les règles des groupes, en mémoire. Perdu au rechargement ; le serveur restera juge. */
import { computed, reactive, ref } from "vue";

import { GROUP_ADMIN_ROLE, MOCK_PEOPLE, MOCK_PERSONAS, mockGroups, mockRoles } from "@/composables/mockGroups";
import type { Version } from "@/types/analyse";
import type {
  AccessContent,
  AnalyseAccess,
  Assignment,
  Group,
  GroupContent,
  Permission,
  Role,
  RoleContent,
} from "@/types/groups";

const roles = ref<Role[]>(mockRoles());
const groups = ref<Group[]>(mockGroups());
const accesses = reactive<Record<string, AnalyseAccess>>({});
const personaId = ref(MOCK_PERSONAS[0].id);
let sequence = 0;

const nextId = () => `mock-${++sequence}`;
const snapshot = <T>(content: T): Version<T> => ({
  id: nextId(),
  content: JSON.parse(JSON.stringify(content)) as T,
  createdAt: new Date().toISOString(),
});

const persona = computed(() => MOCK_PERSONAS.find((p) => p.id === personaId.value)!);
const roleById = (id: string) => roles.value.find((r) => r.id === id);
const groupById = (id: string) => groups.value.find((g) => g.id === id);
const knownPerson = (email: string) => MOCK_PEOPLE.find((p) => p.email === email.trim().toLowerCase());

/** La personne a-t-elle cette permission dans ce groupe ? */
function can(permission: Permission, groupId: string): boolean {
  if (persona.value.superAdmin) return true;
  const mine = groupById(groupId)?.members.find((m) => m.email === persona.value.email);
  return !!mine && !!roleById(mine.roleId)?.permissions.includes(permission);
}

/** Les groupes qu'on voit : tous pour un super admin, sinon les siens. */
const visibleGroups = computed(() =>
  groups.value.filter((g) => persona.value.superAdmin || g.members.some((m) => m.email === persona.value.email)),
);

/** Les groupes auxquels on peut associer une analyse que l'on crée. */
const creationGroups = computed(() => groups.value.filter((g) => can("analyse.create", g.id)));

function log(group: Group, text: string) {
  group.journal.unshift({ id: nextId(), at: new Date().toISOString(), author: persona.value.label, text });
}

const describeRole = (id: string) => roleById(id)?.name ?? "rôle supprimé";

// --- Groupes ---

function saveGroup(content: GroupContent, id?: string): string {
  const existing = id ? groupById(id) : undefined;
  if (existing) {
    existing.versions.push(snapshot({ name: existing.name, description: existing.description }));
    Object.assign(existing, content);
    log(existing, "Groupe modifié");
    return existing.id;
  }
  const group: Group = { id: nextId(), ...content, members: [], versions: [], journal: [] };
  groups.value.push(group);
  log(groupById(group.id)!, "Groupe créé");
  return group.id;
}

function restoreGroup(id: string, versionId: string) {
  const version = groupById(id)?.versions.find((v) => v.id === versionId);
  if (version) saveGroup({ ...version.content }, id);
}

const analysesOf = (groupId: string) => Object.values(accesses).filter((a) => a.groupIds.includes(groupId)).length;

/** Proposition à valider (#661) : un groupe encore utilisé ne se supprime pas. */
const isGroupUsed = (id: string) => !!groupById(id)?.members.length || analysesOf(id) > 0;

function removeGroup(id: string) {
  if (!isGroupUsed(id)) groups.value = groups.value.filter((g) => g.id !== id);
}

function addMember(groupId: string, email: string, roleId: string): string | null {
  const group = groupById(groupId)!;
  const address = email.trim().toLowerCase();
  if (group.members.some((m) => m.email === address)) return "Cette personne est déjà membre du groupe.";
  group.members.push({ email: address, name: knownPerson(address)?.name ?? "", roleId });
  log(group, `${address} ajouté au groupe : ${describeRole(roleId)}`);
  return null;
}

function setMemberRole(groupId: string, email: string, roleId: string) {
  const group = groupById(groupId)!;
  const member = group.members.find((m) => m.email === email);
  if (!member) return;
  log(group, `${email} : ${describeRole(member.roleId)} → ${describeRole(roleId)}`);
  member.roleId = roleId;
}

function removeMember(groupId: string, email: string) {
  const group = groupById(groupId)!;
  group.members = group.members.filter((m) => m.email !== email);
  log(group, `${email} retiré du groupe`);
}

const hasAdmin = (group: Group) => group.members.some((m) => m.roleId === GROUP_ADMIN_ROLE);

// --- Rôles ---

const contentOfRole = ({ name, description, permissions }: RoleContent): RoleContent => ({
  name,
  description,
  permissions: [...permissions],
});

function saveRole(content: RoleContent, id?: string): void {
  const existing = id ? roleById(id) : undefined;
  if (existing?.system) return;
  if (existing) {
    existing.versions.push(snapshot(contentOfRole(existing)));
    Object.assign(existing, contentOfRole(content));
  } else {
    roles.value.push({ id: nextId(), ...contentOfRole(content), system: false, versions: [] });
  }
}

function restoreRole(id: string, versionId: string) {
  const version = roleById(id)?.versions.find((v) => v.id === versionId);
  if (version) saveRole(version.content, id);
}

const isRoleUsed = (id: string) =>
  groups.value.some((g) => g.members.some((m) => m.roleId === id)) ||
  Object.values(accesses).some((a) => a.people.some((p) => p.roleId === id));

function removeRole(id: string) {
  if (!roleById(id)?.system && !isRoleUsed(id)) roles.value = roles.value.filter((r) => r.id !== id);
}

// --- Accès à une analyse ---

/** Maquette : toute analyse réelle part rattachée au groupe « Service culture ». */
function accessOf(analyseId: string): AnalyseAccess {
  accesses[analyseId] ??= { groupIds: ["culture"], people: [], versions: [] };
  return accesses[analyseId];
}

const canManageAccess = (analyseId: string) =>
  persona.value.superAdmin || accessOf(analyseId).groupIds.some((id) => can("analyse.access", id));

function saveAccess(analyseId: string, content: AccessContent) {
  const access = accessOf(analyseId);
  access.versions.push(snapshot({ groupIds: access.groupIds, people: access.people }));
  access.groupIds = [...content.groupIds];
  access.people = content.people.map((p: Assignment) => ({ ...p }));
}

function restoreAccess(analyseId: string, versionId: string) {
  const version = accessOf(analyseId).versions.find((v) => v.id === versionId);
  if (version) saveAccess(analyseId, version.content);
}

/** Pour les tests : repartir des données d'origine. */
export function resetMockGroups() {
  roles.value = mockRoles();
  groups.value = mockGroups();
  for (const key of Object.keys(accesses)) delete accesses[key];
  personaId.value = MOCK_PERSONAS[0].id;
}

export function useGroups() {
  return {
    roles,
    groups,
    visibleGroups,
    creationGroups,
    persona,
    personaId,
    personas: MOCK_PERSONAS,
    people: MOCK_PEOPLE,
    can,
    roleById,
    groupById,
    knownPerson,
    saveGroup,
    restoreGroup,
    isGroupUsed,
    removeGroup,
    addMember,
    setMemberRole,
    removeMember,
    hasAdmin,
    saveRole,
    restoreRole,
    isRoleUsed,
    removeRole,
    accessOf,
    canManageAccess,
    saveAccess,
    restoreAccess,
  };
}
