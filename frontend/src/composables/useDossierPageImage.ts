import { computed, ref, toValue, watch, type MaybeRefOrGetter } from "vue";

import { loadScreenshot, peekScreenshot, screenshotKey } from "@/utils/pageScreenshotCache";

/**
 * La capture d'une page d'un document du dossier, pour l'aperçu d'une source. La route demande la session de la
 * personne : on charge l'image avec les cookies et on en fait une URL locale, libérée quand la carte disparaît. Une
 * page sans capture (404) n'a simplement pas d'aperçu.
 */
export function useDossierPageImage(
  dossierId: MaybeRefOrGetter<string>,
  documentId: MaybeRefOrGetter<string | undefined>,
  pageId: MaybeRefOrGetter<string | undefined>
) {
  // Une chaîne (valeur primitive) : le watch ne se déclenche que si dossier, document ou page changent vraiment.
  const key = computed(() => {
    const d = toValue(dossierId);
    const doc = toValue(documentId);
    const p = toValue(pageId);
    return d && doc && p ? screenshotKey(d, doc, p) : null;
  })

  const url = ref<string | null>(null);

  watch(
    key,
    async (current) => {
      if (!current) {
        url.value = null;
        return;
      }
      const known = peekScreenshot(current);
      if(known !== undefined) {
        url.value = known; // déjà en cache : affichage immédiat, sans aucun aller-retour
        return;
      }
      // `url` n'est volontairement pas remis à null ici : l'ancienne image reste jusqu'à l'arrivée de la nouvelle.
      const shot = await loadScreenshot(toValue(dossierId), toValue(documentId)!, toValue(pageId)!);
      if (key.value == current) url.value = shot; // la source a pu changer pendant le chargement
    },
    { immediate : true },
  ); 

  return { url };
}
