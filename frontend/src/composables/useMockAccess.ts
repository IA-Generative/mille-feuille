/** Maquette des accès à une analyse (#662) : en mémoire, sans appel au backend. Perdu au rechargement. */
import { computed, reactive, ref } from "vue";

import { GROUP_ADMIN_ROLE, MOCK_PEOPLE, MOCK_PERSONAS, mockGroups, mockRoles } from "@/composables/mockGroups";
import type { Version } from "@/types/analyse";
import type { AccessContent, AnalyseAccess } from "@/types/mockAccess";

const roles = mockRoles();
const groups = mockGroups();
const accesses = reactive<Record<string, AnalyseAccess>>({});
const personaId = ref(MOCK_PERSONAS[0].id);
let sequence = 0;

const persona = computed(() => MOCK_PERSONAS.find((p) => p.id === personaId.value)!);
const groupById = (id: string) => groups.find((g) => g.id === id);
const roleById = (id: string) => roles.find((r) => r.id === id);
const knownPerson = (email: string) => MOCK_PEOPLE.find((p) => p.email === email.trim().toLowerCase());
const snapshot = (content: AccessContent): Version<AccessContent> => ({
  id: `mock-${++sequence}`,
  content: JSON.parse(JSON.stringify(content)) as AccessContent,
  createdAt: new Date().toISOString(),
});

/** Gère les accès : un super admin, ou l'admin d'un groupe. */
const managesAccessIn = (groupId: string) =>
  persona.value.superAdmin ||
  !!groupById(groupId)?.members.some((m) => m.email === persona.value.email && m.roleId === GROUP_ADMIN_ROLE);

const creationGroups = computed(() => groups.filter((g) => managesAccessIn(g.id)));

/** Toute analyse réelle part rattachée au groupe « Service culture ». */
function accessOf(analyseId: string): AnalyseAccess {
  accesses[analyseId] ??= { groupIds: ["culture"], people: [], versions: [] };
  return accesses[analyseId];
}

const canManageAccess = (analyseId: string) =>
  persona.value.superAdmin || accessOf(analyseId).groupIds.some(managesAccessIn);

function saveAccess(analyseId: string, content: AccessContent) {
  const access = accessOf(analyseId);
  access.versions.push(snapshot({ groupIds: access.groupIds, people: access.people }));
  access.groupIds = [...content.groupIds];
  access.people = content.people.map((p) => ({ ...p }));
}

function restoreAccess(analyseId: string, versionId: string) {
  const version = accessOf(analyseId).versions.find((v) => v.id === versionId);
  if (version) saveAccess(analyseId, version.content);
}

/** Pour les tests : repartir des données d'origine. */
export function resetMockAccess() {
  for (const key of Object.keys(accesses)) delete accesses[key];
  personaId.value = MOCK_PERSONAS[0].id;
}

export function useMockAccess() {
  return {
    roles,
    groups,
    creationGroups,
    persona,
    personaId,
    personas: MOCK_PERSONAS,
    groupById,
    roleById,
    knownPerson,
    managesAccessIn,
    accessOf,
    canManageAccess,
    saveAccess,
    restoreAccess,
  };
}
