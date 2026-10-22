import type { Tool, ToolAuthMode, ToolServer, ToolVisibility } from "@/types/tool";

// Les formes renvoyées par l'API (snake_case), et leur passage au camelCase du frontend.

export interface ToolOut {
  id: string;
  name: string;
  description: string;
  kind: "internal" | "mcp";
  server_id: string | null;
  side_effect: boolean;
  enabled: boolean;
  config: "collections" | null;
}

export interface ToolServerOut {
  id: string;
  name: string;
  url: string;
  auth_mode: ToolAuthMode;
  audience: string | null;
  visibility: ToolVisibility;
  owner_name: string;
  owned_by_me: boolean;
  synced_at: string;
  tools: ToolOut[];
}

export interface DiscoveredToolOut {
  name: string;
  description: string;
  side_effect: boolean;
}

export function toTool(raw: ToolOut): Tool {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    kind: raw.kind,
    serverId: raw.server_id,
    sideEffect: raw.side_effect,
    enabled: raw.enabled,
    ...(raw.config ? { config: raw.config } : {}),
  };
}

export function toToolServer(raw: ToolServerOut): ToolServer {
  return {
    id: raw.id,
    name: raw.name,
    url: raw.url,
    authMode: raw.auth_mode,
    audience: raw.audience,
    visibility: raw.visibility,
    ownerName: raw.owner_name,
    ownedByMe: raw.owned_by_me,
    syncedAt: raw.synced_at,
    tools: raw.tools.map(toTool),
  };
}

/** Un tool découvert sur un serveur pas encore ajouté : il n'a pas d'identifiant, on se sert de son nom. */
export function toPreviewTool(raw: DiscoveredToolOut): Tool {
  return {
    id: raw.name,
    name: raw.name,
    description: raw.description,
    kind: "mcp",
    serverId: null,
    sideEffect: raw.side_effect,
    enabled: true,
  };
}
