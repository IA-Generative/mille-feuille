import { API_BASE_URL } from "@/utils/api";

/** `string` = capture prête (URL locale) ; `null` = pas de capture (404, on ne réessaie pas). */
type Shot = string | null;

const resolved = new Map<string, Shot>();
const pending = new Map<string, Promise<Shot>>();

export const screenshotKey = (dossierId: string, documentId: string, pageId: string) =>
  `${dossierId}/${documentId}/${pageId}`;

/** Lecture synchrone : `undefined` = pas encore connue. Évite un rendu « vide » quand la capture est déjà en cache. */
export const peekScreenshot = (key: string): Shot | undefined => resolved.get(key);

async function fetchScreenshot(dossierId: string, documentId: string, pageId: string): Promise<Shot> {
  const response = await fetch(
    `${API_BASE_URL}/api/dossiers/${dossierId}/documents/${documentId}/pages/${pageId}/screenshot`,
    { credentials: "include" },
  );
  if (response.status === 404) return null; // pas de capture : définitif
  if (!response.ok) throw new Error(String(response.status)); // erreur passagère : on pourra réessayer
  return URL.createObjectURL(await response.blob());
}

export function loadScreenshot(dossierId: string, documentId: string, pageId: string): Promise<Shot> {
  const key = screenshotKey(dossierId, documentId, pageId);
  if (resolved.has(key)) return Promise.resolve(resolved.get(key) ?? null);
  const inflight = pending.get(key);
  if (inflight) return inflight;

  const request: Promise<Shot> = fetchScreenshot(dossierId, documentId, pageId)
    .then((shot) => {
      // Le dossier a été quitté pendant le téléchargement : on libère tout de suite, personne n'en veut.
      if (pending.get(key) !== request) {
        if (shot) URL.revokeObjectURL(shot);
        return null;
      }
      resolved.set(key, shot);
      return shot;
    })
    .catch(() => null) // non mémorisé : un prochain affichage retentera
    .finally(() => {
      if (pending.get(key) === request) pending.delete(key);
    });

  pending.set(key, request);
  return request;
}

/** À appeler quand on quitte le dossier : libère les URL locales et vide le cache de ce dossier. */
export function releaseDossierScreenshots(dossierId: string) {
  const prefix = `${dossierId}/`;
  for (const [key, shot] of resolved) {
    if (!key.startsWith(prefix)) continue;
    if (shot) URL.revokeObjectURL(shot);
    resolved.delete(key);
  }
  for (const key of pending.keys()) if (key.startsWith(prefix)) pending.delete(key);
}