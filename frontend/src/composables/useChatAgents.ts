import { ref, type Ref } from "vue";

import type { ChatAgent } from "@/types/chatAgent";

// Les agents de l'analyse du dossier, interrogeables dans le chat. Pour l'instant des données simulées : la signature
// (`load()`, `agents`, `error`) est celle qu'aura la lecture de l'API (GET /api/dossiers/{id}/agents), pour que le
// composant n'ait pas à changer. Le premier appel simule un temps de réponse court.

const MOCK_AGENTS: ChatAgent[] = [
  { name: "Juriste", role: "Analyse les clauses juridiques et les obligations des parties." },
  { name: "Comptable", role: "Vérifie les montants, les charges et les totaux." },
  { name: "Planificateur", role: "Construit le calendrier des échéances et des délais." },
];

export function useChatAgents(_dossierId: string): {
  agents: Ref<ChatAgent[]>;
  error: Ref<string>;
  load: () => Promise<void>;
} {
  const agents = ref<ChatAgent[]>([]);
  const error = ref("");

  async function load() {
    error.value = "";
    await new Promise((resolve) => setTimeout(resolve, 150));
    agents.value = MOCK_AGENTS;
  }

  return { agents, error, load };
}
