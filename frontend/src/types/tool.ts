export type ToolKind = "internal" | "mcp";

/**
 * Comment la plateforme s'authentifie auprès d'un serveur MCP. `static_token`
 * est prévu dans le modèle mais pas encore activable.
 */
export type ToolAuthMode = "none" | "token_exchange" | "static_token";

export const TOOL_AUTH_LABELS: Record<ToolAuthMode, string> = {
  none: "Sans authentification",
  token_exchange: "Identité de l'utilisateur",
  static_token: "Jeton statique",
};

export type ToolVisibility = "private" | "groups" | "all";

export const TOOL_VISIBILITY_LABELS: Record<ToolVisibility, string> = {
  private: "Privé",
  groups: "Mes groupes",
  all: "Toute la plateforme",
};

/** Résultat d'un test unitaire : la sortie brute du tool, sa durée et son issue. */
export interface ToolTestRun {
  ok: boolean;
  /** Code d'échec stable (`delai_depasse`, `aucun_appel`…), absent en cas de succès. */
  code: string | null;
  /** La sortie du tool, ou le message d'erreur en français. */
  output: string;
  truncated: boolean;
  durationMs: number;
  /** Le modèle qui a choisi les arguments. */
  model: string | null;
  /** L'appel que le modèle a fait : le nom du tool et les arguments qu'il a choisis. */
  call: { name: string; arguments: Record<string, unknown> } | null;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  kind: ToolKind;
  /** Null pour un tool interne. */
  serverId: string | null;
  /** Un tool qui modifie quelque chose demande une confirmation avant appel dans le chat. */
  sideEffect: boolean;
  /** Autorisé par la personne qui a ajouté le serveur (toujours vrai pour un tool interne). */
  enabled: boolean;
  /** Un tool qui demande une configuration par analyse (ex : les collections de la base de connaissances). */
  config?: "collections";
}

export interface ToolServer {
  id: string;
  name: string;
  url: string;
  authMode: ToolAuthMode;
  /** Client Keycloak du serveur (mode « identité de l'utilisateur »). */
  audience: string | null;
  visibility: ToolVisibility;
  ownerName: string;
  ownedByMe: boolean;
  /** Date du dernier import de la liste de tools (`tools/list`). */
  syncedAt: string;
  tools: Tool[];
}

export interface ToolServerDraft {
  name: string;
  url: string;
  authMode: ToolAuthMode;
  /** Obligatoire pour l'identité de l'utilisateur ; vide sinon. */
  audience: string;
  visibility: ToolVisibility;
}
