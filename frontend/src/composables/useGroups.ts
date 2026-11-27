/** Groupes, rôles et membres, branchés sur l'API. */
import { ref } from "vue";

import type { FieldVersion, Group, GroupEvent, Member, Role } from "@/types/groups";
import { apiFetch } from "@/utils/api";

const mapVersion = (api: any): FieldVersion => ({
  id: api.id,
  content: { field: api.field, value: api.content },
  createdAt: api.created_at,
});

const mapGroup = (api: any): Group => ({
  id: api.id,
  name: api.name,
  description: api.description,
  memberCount: api.member_count,
  canManageMembers: api.can_manage_members,
  canCreateAnalyses: api.can_create_analyses,
  deletable: api.deletable,
  versions: api.versions.map(mapVersion),
});

const mapRole = (api: any): Role => ({
  id: api.id,
  name: api.name,
  description: api.description,
  permissions: api.permissions,
  system: api.system,
  inUse: api.in_use,
  assignable: api.assignable,
  versions: api.versions.map(mapVersion),
});

const mapMember = (api: any): Member => ({
  id: api.id,
  name: api.name,
  email: api.email,
  roleId: api.role_id,
  pending: api.pending,
  editable: api.editable,
});

const mapEvent = (api: any): GroupEvent => ({
  id: api.id,
  type: api.type,
  createdAt: api.created_at,
  actorName: api.actor_name,
  subject: api.subject,
  roleName: api.role_name,
  previousRoleName: api.previous_role_name,
});

const groups = ref<Group[]>([]);
const roles = ref<Role[]>([]);

const send = <T>(path: string, method: string, body?: unknown) =>
  apiFetch<T>(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

export function useGroups() {
  async function fetchGroups() {
    groups.value = (await apiFetch<any[]>("/api/groups")).map(mapGroup);
  }

  async function saveGroup(content: { name: string; description: string }, id?: string): Promise<string> {
    const saved = await send<any>(id ? `/api/groups/${id}` : "/api/groups", id ? "PUT" : "POST", content);
    await fetchGroups();
    return saved.id;
  }

  async function restoreGroup(id: string, versionId: string) {
    await send(`/api/groups/${id}/restore/${versionId}`, "POST");
    await fetchGroups();
  }

  async function removeGroup(id: string) {
    await send(`/api/groups/${id}`, "DELETE");
    await fetchGroups();
  }

  /** `groupId` : marque les rôles que la personne peut attribuer dans ce groupe. */
  async function fetchRoles(groupId?: string): Promise<Role[]> {
    const list = (await apiFetch<any[]>(`/api/roles${groupId ? `?group_id=${groupId}` : ""}`)).map(mapRole);
    if (!groupId) roles.value = list;
    return list;
  }

  async function saveRole(content: { name: string; description: string; permissions: string[] }, id?: string) {
    await send(id ? `/api/roles/${id}` : "/api/roles", id ? "PUT" : "POST", content);
    await fetchRoles();
  }

  async function restoreRole(id: string, versionId: string) {
    await send(`/api/roles/${id}/restore/${versionId}`, "POST");
    await fetchRoles();
  }

  async function removeRole(id: string) {
    await send(`/api/roles/${id}`, "DELETE");
    await fetchRoles();
  }

  const fetchMembers = async (groupId: string) =>
    (await apiFetch<any[]>(`/api/groups/${groupId}/members`)).map(mapMember);

  const fetchEvents = async (groupId: string) =>
    (await apiFetch<any[]>(`/api/groups/${groupId}/events`)).map(mapEvent);

  const addMember = (groupId: string, who: { email: string } | { userId: string }, roleId: string) =>
    send(`/api/groups/${groupId}/members`, "POST", {
      ...("userId" in who ? { user_id: who.userId } : { email: who.email }),
      role_id: roleId,
    });

  const setMemberRole = (groupId: string, memberId: string, roleId: string) =>
    send(`/api/groups/${groupId}/members/${memberId}`, "PATCH", { role_id: roleId });

  const removeMember = (groupId: string, memberId: string) =>
    send(`/api/groups/${groupId}/members/${memberId}`, "DELETE");

  /** Les personnes connues de l'application, par nom : leur adresse n'est pas diffusée. */
  const searchPeople = (query: string) =>
    apiFetch<{ id: string; name: string }[]>(`/api/users?limit=10&q=${encodeURIComponent(query)}`);

  return {
    groups,
    roles,
    fetchGroups,
    saveGroup,
    restoreGroup,
    removeGroup,
    fetchRoles,
    saveRole,
    restoreRole,
    removeRole,
    fetchMembers,
    fetchEvents,
    addMember,
    setMemberRole,
    removeMember,
    searchPeople,
  };
}
