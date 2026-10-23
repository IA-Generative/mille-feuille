import { onBeforeUnmount, ref, watch, type Ref } from "vue";

import { API_BASE_URL } from "@/utils/api";

/**
 * La capture d'une page d'un document du dossier, pour l'aperçu d'une source. La route demande la session de la
 * personne : on charge l'image avec les cookies et on en fait une URL locale, libérée quand la carte disparaît. Une
 * page sans capture (404) n'a simplement pas d'aperçu.
 */
export function useDossierPageImage(
  dossierId: Ref<string>,
  target: Ref<{ documentId: string; pageId: string } | null>,
) {
  const url = ref<string | null>(null);
  let token = 0;

  function release() {
    if (url.value) URL.revokeObjectURL(url.value);
    url.value = null;
  }

  async function load() {
    release();
    const wanted = target.value;
    if (!wanted) return;
    const current = ++token;
    try {
      const path = `/api/dossiers/${dossierId.value}/documents/${wanted.documentId}/pages/${wanted.pageId}/screenshot`;
      const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
      if (current !== token || !response.ok) return;
      url.value = URL.createObjectURL(await response.blob());
    } catch {
      // Pas de capture : la carte s'affiche sans aperçu.
    }
  }

  watch(target, load, { immediate: true });
  onBeforeUnmount(() => {
    token++;
    release();
  });

  return { url };
}
