/** Un outil que l'analyse autorise pour le chat d'un dossier, tel que cette personne peut l'utiliser. */
export interface ChatTool {
  id: string;
  name: string;
  description: string;
  kind: "internal" | "mcp";
  /** Le serveur MCP d'où il vient ; null pour un outil interne. */
  serverName: string | null;
  /** Il modifie des données : il demandera une confirmation. */
  sideEffect: boolean;
}
