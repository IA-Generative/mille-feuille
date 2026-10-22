import { ref } from "vue";

import { TOOLS_PREVIEW } from "@/utils/featureFlags";

// Données simulées (phase 1, docs/tools-mcp-plan.md) : demande de confirmation avant l'appel d'un tool qui modifie
// des données. Le vrai flux viendra du worker (événement de chat) ; ici on ne garde que la forme.

export interface PendingToolCall {
  toolName: string;
  serverName: string | null;
  /** Arguments que le modèle veut passer au tool, lisibles par la personne. */
  args: Record<string, string>;
}

const pendingToolCall = ref<PendingToolCall | null>(null);

export function useToolConfirmation() {
  const resolveToolCall = (_allowed: boolean) => {
    pendingToolCall.value = null;
  };
  const requestToolCall = (call: PendingToolCall) => {
    pendingToolCall.value = call;
  };
  return { pendingToolCall, requestToolCall, resolveToolCall };
}

// Permet de déclencher la demande à la main pendant la maquette (captures d'écran).
if (import.meta.env.DEV && TOOLS_PREVIEW) {
  (window as unknown as { __toolsMock: object }).__toolsMock = {
    askConfirmation: () =>
      useToolConfirmation().requestToolCall({
        toolName: "envoyer_courriel",
        serverName: "Annuaire des services",
        args: { destinataire: "service-subventions@culture.example.gouv.fr", objet: "Pièce manquante : RIB de l'association" },
      }),
  };
}
