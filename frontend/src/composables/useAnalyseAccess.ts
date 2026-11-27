import type { AccessPerson, AnalyseAccess } from "@/types/analyseAccess";
import { apiFetch } from "@/utils/api";

function mapAccess(api: any): AnalyseAccess {
  return {
    canEdit: api.can_edit,
    groups: api.groups,
    availableGroups: api.available_groups,
    people: api.people.map((p: any) => ({
      id: p.id,
      name: p.name,
      email: p.email,
      roleId: p.role_id,
      pending: p.pending,
      editable: p.editable,
    })),
    assignableRoleIds: api.assignable_role_ids,
    versions: api.versions.map((v: any) => ({
      id: v.id,
      createdAt: v.created_at,
      content: { groups: v.groups, people: v.people },
    })),
  };
}

/** Une personne déjà ajoutée est désignée par son identifiant ; une nouvelle, par son compte ou son adresse. */
const personBody = (p: AccessPerson) => ({
  ...(p.id ? { id: p.id } : p.userId ? { user_id: p.userId } : { email: p.email }),
  role_id: p.roleId,
});

export function useAnalyseAccess(analyseId: () => string) {
  const url = () => `/api/analyses/${analyseId()}/access`;

  const fetchAccess = async () => mapAccess(await apiFetch<any>(url()));

  async function saveAccess(groupIds: string[], people: AccessPerson[]) {
    const body = JSON.stringify({ group_ids: groupIds, people: people.map(personBody) });
    return mapAccess(await apiFetch<any>(url(), { method: "PUT", body }));
  }

  const restoreAccess = async (versionId: string) =>
    mapAccess(await apiFetch<any>(`${url()}/restore/${versionId}`, { method: "POST" }));

  return { fetchAccess, saveAccess, restoreAccess };
}
