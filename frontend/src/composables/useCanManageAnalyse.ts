import { useAuth } from "@/composables/useAuth";

/**
 * Qui peut modifier le nom et la description d'une analyse, la restaurer ou la supprimer : son créateur et les
 * administrateurs (même règle que le backend, qui reste juge : 403 sinon). Une analyse sans créateur connu n'est gérée
 * que par les administrateurs.
 */
export function useCanManageAnalyse() {
  const { isAdmin, profile } = useAuth();
  return (createdBy: string | null) =>
    isAdmin.value || (createdBy !== null && createdBy === profile.value?.userId);
}
