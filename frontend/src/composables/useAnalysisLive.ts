import { computed, onBeforeUnmount, ref, type Ref } from "vue";

import { useAuth } from "@/composables/useAuth";
import { API_BASE_URL, apiFetch, userMessage } from "@/utils/api";

// Travail à plusieurs sur l'analyse de dossier (backend issue #118) : présence
// des autres instructeurs, verrou court par élément et flux temps réel (SSE).

export interface PresenceEntry {
  userId: string;
  displayName: string;
  elementId: string | null;
  mode: "viewing" | "editing";
  updatedAt: string;
}

export interface LockEntry {
  elementId: string;
  lockedBy: string;
  lockedByName: string | null;
  lockedUntil: string;
  heldByMe: boolean;
}

export type LockResult = { ok: true } | { ok: false; message: string };

function mapPresence(api: any): PresenceEntry {
  return {
    userId: api.user_id,
    displayName: api.display_name,
    elementId: api.element_id,
    mode: api.mode,
    updatedAt: api.updated_at,
  };
}

function mapLock(api: any): LockEntry {
  return {
    elementId: api.element_id,
    lockedBy: api.locked_by,
    lockedByName: api.locked_by_name,
    lockedUntil: api.locked_until,
    heldByMe: api.held_by_me,
  };
}

// Le serveur invalide un verrou au bout de 60 s sans renouvellement et ignore une
// présence au bout de 30 s : on renouvelle bien avant (voir CollaborationSettings).
const HEARTBEAT_MS = 15_000;
const LOCK_RENEW_MS = 20_000;
// Un verrou n'est renouvelé que tant que l'instructeur écrit : sans saisie depuis ce délai
// (onglet laissé ouvert), on cesse de le renouveler et il expire seul.
const LOCK_IDLE_MS = 5 * 60_000;

/**
 * Présence et verrou d'une analyse de dossier. Actif tant que `analysisId` est
 * renseigné (analyse courante et modifiable) : ouvre le flux SSE, envoie un battement
 * de cœur de présence et gère le verrou de l'élément en cours d'édition (renouvelé
 * tant que l'édition dure, libéré à la fin). Tout est libéré à la fermeture de la page.
 */
export function useAnalysisLive(dossierId: string, analysisId: Ref<string | undefined>) {
  const { profile } = useAuth();
  const presence = ref<PresenceEntry[]>([]);
  const locks = ref<LockEntry[]>([]);

  let source: EventSource | undefined;
  let heartbeat: ReturnType<typeof setInterval> | undefined;
  let renew: ReturnType<typeof setInterval> | undefined;
  let focus: { elementId: string | null; mode: "viewing" | "editing" } = { elementId: null, mode: "viewing" };
  let heldLock: string | undefined;
  let connectedTo: string | undefined;
  let lastActivity = Date.now();

  const base = (id: string) => `/api/dossiers/${dossierId}/analyses-dossier/${id}`;

  /** Les autres instructeurs, par élément. */
  const othersByElement = computed(() => {
    const map = new Map<string, PresenceEntry[]>();
    for (const entry of presence.value) {
      if (entry.userId === profile.value?.userId || !entry.elementId) continue;
      map.set(entry.elementId, [...(map.get(entry.elementId) ?? []), entry]);
    }
    return map;
  });

  /** Les autres instructeurs présents sur l'analyse (n'importe où). */
  const others = computed(() => presence.value.filter((entry) => entry.userId !== profile.value?.userId));

  /** Verrous détenus par quelqu'un d'autre, par élément. */
  const lockedByOthers = computed(() => {
    const map = new Map<string, LockEntry>();
    for (const lock of locks.value) if (!lock.heldByMe) map.set(lock.elementId, lock);
    return map;
  });

  async function sendHeartbeat() {
    const id = connectedTo;
    if (!id) return;
    try {
      await apiFetch(`${base(id)}/presence`, {
        method: "PUT",
        body: JSON.stringify({ element_id: focus.elementId, mode: focus.mode }),
      });
    } catch {
      // Un battement raté n'est pas grave : le prochain rattrape, la présence expire seule.
    }
  }

  /** Indique sur quel élément on est (null : sur l'analyse, sans élément précis). */
  function setFocus(elementId: string | null, mode: "viewing" | "editing" = "viewing") {
    focus = { elementId, mode };
    void sendHeartbeat();
  }

  function stopTimers() {
    if (heartbeat) clearInterval(heartbeat);
    if (renew) clearInterval(renew);
    heartbeat = renew = undefined;
  }

  /** Prend le verrou avant de modifier un élément. Refus (409) : le message dit qui le détient. */
  async function acquireLock(elementId: string): Promise<LockResult> {
    const id = connectedTo;
    if (!id) return { ok: true }; // pas de travail à plusieurs sur cette analyse (ancienne exécution)
    try {
      await apiFetch(`${base(id)}/elements/${elementId}/lock`, { method: "POST" });
    } catch (e) {
      return { ok: false, message: userMessage(e, "Impossible de verrouiller cet élément.") };
    }
    heldLock = elementId;
    lastActivity = Date.now();
    if (renew) clearInterval(renew);
    renew = setInterval(() => {
      if (!heldLock) return;
      if (Date.now() - lastActivity > LOCK_IDLE_MS) {
        // Inactif depuis trop longtemps : on ne renouvelle plus, le verrou expire seul.
        if (renew) clearInterval(renew);
        renew = undefined;
        return;
      }
      // Renouvellement : si un autre l'a pris entre-temps, l'enregistrement sera refusé avec un message clair.
      void apiFetch(`${base(id)}/elements/${heldLock}/lock`, { method: "POST" }).catch(() => undefined);
    }, LOCK_RENEW_MS);
    setFocus(elementId, "editing");
    return { ok: true };
  }

  /** À appeler à chaque saisie : tant que l'instructeur écrit, son verrou est renouvelé. */
  function touchActivity() {
    lastActivity = Date.now();
  }

  /** Libère le verrou (déjà libéré par le serveur après un enregistrement réussi). */
  async function releaseLock() {
    const id = connectedTo;
    const element = heldLock;
    heldLock = undefined;
    if (renew) clearInterval(renew);
    renew = undefined;
    setFocus(null, "viewing");
    if (!id || !element) return;
    try {
      await apiFetch(`${base(id)}/elements/${element}/lock`, { method: "DELETE" });
    } catch {
      // Le verrou expire seul.
    }
  }

  function connect(id: string) {
    disconnect();
    connectedTo = id;
    source = new EventSource(`${API_BASE_URL}${base(id)}/live`, { withCredentials: true });
    source.addEventListener("live", (event) => {
      const data = JSON.parse((event as MessageEvent).data);
      presence.value = (data.presence ?? []).map(mapPresence);
      locks.value = (data.locks ?? []).map(mapLock);
    });
    // Le navigateur reconnecte seul en cas de coupure réseau : on laisse faire.
    void sendHeartbeat();
    heartbeat = setInterval(() => void sendHeartbeat(), HEARTBEAT_MS);
  }

  function disconnect() {
    const id = connectedTo;
    const element = heldLock;
    stopTimers();
    source?.close();
    source = undefined;
    connectedTo = undefined;
    heldLock = undefined;
    presence.value = [];
    locks.value = [];
    if (id) {
      // Meilleur effort à la fermeture : sinon le verrou et la présence expirent seuls.
      void apiFetch(`${base(id)}/presence`, { method: "DELETE", keepalive: true } as RequestInit).catch(() => undefined);
      if (element) void apiFetch(`${base(id)}/elements/${element}/lock`, { method: "DELETE", keepalive: true } as RequestInit).catch(() => undefined);
    }
  }

  /** (Re)branche sur l'analyse donnée, ou débranche si elle n'est plus modifiable. */
  function sync(id: string | undefined) {
    if (id === connectedTo) return;
    if (id) connect(id);
    else disconnect();
  }

  onBeforeUnmount(disconnect);

  return { presence, locks, others, othersByElement, lockedByOthers, sync, setFocus, acquireLock, releaseLock, touchActivity };
}
