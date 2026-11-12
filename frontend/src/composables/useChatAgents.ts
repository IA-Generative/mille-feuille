import { ref } from "vue";

import type { ChatAgent } from "@/types/chatAgent";
import { apiFetch, userMessage } from "@/utils/api";

// Les agents de l'analyse du dossier, interrogeables dans le chat (en les nommant avec @Nom, ou en laissant le chat
// choisir). Lecture seule : ils se définissent dans l'analyse.

export function useChatAgents(dossierId: string) {
  const agents = ref<ChatAgent[]>([]);
  const error = ref("");

  async function load() {
    error.value = "";
    try {
      agents.value = await apiFetch<ChatAgent[]>(`/api/dossiers/${dossierId}/agents`);
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger les agents.");
    }
  }

  return { agents, error, load };
}
