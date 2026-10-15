import { onBeforeUnmount, ref } from "vue";

const FEEDBACK_MS = 1500;

/** Copie un texte dans le presse-papiers. `copied` désigne la clé du dernier texte copié, le temps d'un retour visuel. */
export function useClipboard() {
  const copied = ref<string | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  // Repli pour les contextes sans API Clipboard (page servie en http hors localhost, navigateur ancien).
  const legacyCopy = (text: string) => {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      return document.execCommand("copy");
    } finally {
      area.remove();
    }
  };

  const copy = async (key: string, text: string) => {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      ok = legacyCopy(text);
    }
    if (!ok) return;
    copied.value = key;
    clearTimeout(timer);
    timer = setTimeout(() => (copied.value = null), FEEDBACK_MS);
  };

  onBeforeUnmount(() => clearTimeout(timer));
  return { copied, copy };
}
