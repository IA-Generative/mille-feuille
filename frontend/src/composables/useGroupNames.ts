/** Les accès désignent un groupe par son identifiant : on affiche son nom. */
import { reactive } from "vue";

import { groupLabel } from "@/types/access";
import { apiFetch } from "@/utils/api";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const names = reactive(new Map<string, string>());
const asked = new Set<string>();

export const isGroupId = (key: string) => UUID.test(key);

export function useGroupNames() {
  /** Demande les noms pas encore connus ; en cas d'échec, ils seront redemandés. */
  async function resolve(keys: string[]) {
    const missing = keys.filter((key) => isGroupId(key) && !asked.has(key));
    if (!missing.length) return;
    missing.forEach((key) => asked.add(key));
    try {
      const query = missing.map((key) => `ids=${encodeURIComponent(key)}`).join("&");
      for (const group of await apiFetch<{ id: string; name: string }[]>(`/api/groups/names?${query}`)) {
        names.set(group.id, group.name);
      }
    } catch {
      missing.forEach((key) => asked.delete(key));
    }
  }

  const nameOf = (key: string) => names.get(key) ?? (isGroupId(key) ? "Groupe" : groupLabel(key));

  return { resolve, nameOf };
}
