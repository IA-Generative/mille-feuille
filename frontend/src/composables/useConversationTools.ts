import { ref, type Ref } from "vue";

import type { ChatTool } from "@/types/chatTool";
import { apiFetch } from "@/utils/api";

// Les outils d'une conversation du chat : ceux que l'analyse autorise (ses agents), moins ceux que la personne a
// retirés. Par défaut tout est actif et le modèle choisit ; la personne ne peut que retirer.

interface ChatToolOut {
  id: string;
  name: string;
  description: string;
  kind: "internal" | "mcp";
  server_name: string | null;
  side_effect: boolean;
  given_to_model: boolean;
}

interface ConversationToolsOut {
  tools: ChatToolOut[];
  excluded: string[];
  unavailable: string[];
}

const toChatTool = (raw: ChatToolOut): ChatTool => ({
  id: raw.id,
  name: raw.name,
  description: raw.description,
  kind: raw.kind,
  serverName: raw.server_name,
  sideEffect: raw.side_effect,
  givenToModel: raw.given_to_model,
});

export function useConversationTools(dossierId: string, conversationId: Ref<string | undefined>) {
  const tools = ref<ChatTool[]>([]);
  const excluded = ref<string[]>([]);
  const unavailable = ref<string[]>([]);
  const error = ref("");

  const url = () => `/api/dossiers/${dossierId}/conversations/${conversationId.value}/tools`;

  function apply(data: ConversationToolsOut) {
    tools.value = data.tools.map(toChatTool);
    excluded.value = data.excluded;
    unavailable.value = data.unavailable;
  }

  async function load() {
    if (!conversationId.value) return;
    error.value = "";
    try {
      apply(await apiFetch<ConversationToolsOut>(url()));
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Impossible de charger les outils.";
    }
  }

  /** Retire ces outils pour la conversation (les autres restent actifs). La liste change tout de suite, puis l'API confirme. */
  async function setExcluded(ids: string[]) {
    if (!conversationId.value) return;
    const previous = excluded.value;
    excluded.value = ids;
    try {
      apply(await apiFetch<ConversationToolsOut>(url(), { method: "PUT", body: JSON.stringify({ excluded: ids }) }));
    } catch (e) {
      excluded.value = previous;
      error.value = e instanceof Error ? e.message : "Impossible d'enregistrer ce choix.";
    }
  }

  return { tools, excluded, unavailable, error, load, setExcluded };
}
