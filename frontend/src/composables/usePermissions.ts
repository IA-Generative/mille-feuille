/** Ce que la personne connectée peut faire sur un dossier ou une analyse, pour masquer ou désactiver. Le serveur reste
 * juge : une action non permise répond 403. */
import { computed, ref, watch } from "vue";

import { useAuth } from "@/composables/useAuth";
import { apiFetch } from "@/utils/api";

export function usePermissions(kind: "dossiers" | "analyses", id: () => string | undefined) {
  const { isAdmin } = useAuth();
  const granted = ref<Set<string> | null>(null);

  watch(
    [id, isAdmin],
    async ([current, admin]) => {
      granted.value = null;
      if (!current || admin) return;
      try {
        const data = await apiFetch<{ permissions: string[] }>(`/api/${kind}/${current}/permissions`);
        if (id() === current) granted.value = new Set(data.permissions);
      } catch {
        // Droits inconnus : rien n'est masqué, le serveur refusera ce qui doit l'être.
      }
    },
    { immediate: true },
  );

  const loaded = computed(() => isAdmin.value || granted.value !== null);
  const can = (permission: string) => isAdmin.value || (granted.value?.has(permission) ?? true);

  return { can, loaded };
}
