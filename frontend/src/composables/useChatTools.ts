import { useTools } from "@/composables/useTools";

// Outils proposés dans le chat d'un dossier (phase 7 du plan) : SIMULÉ. En vrai : ceux des agents de l'analyse,
// filtrés par les droits de la personne. Pour l'instant, tous les outils disponibles.
export function useChatTools() {
  const { allTools } = useTools();
  const chatToolIds = () => allTools().map((tool) => tool.id);
  return { chatToolIds };
}
