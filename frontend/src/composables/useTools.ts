import { ref } from "vue";

import type { Page } from "@/types/pagination";
import type { Tool, ToolServer, ToolServerDraft } from "@/types/tool";
import { apiFetch } from "@/utils/api";
import {
  toPreviewTool,
  toTool,
  toToolServer,
  type DiscoveredToolOut,
  type ToolOut,
  type ToolServerOut,
} from "@/utils/toolMapping";

// Le registre des tools : les tools internes de la plateforme et les serveurs MCP ajoutés par les utilisateurs.
// L'état est partagé (module) : la page « Mes outils », le sélecteur de l'agent et le menu du chat voient la même liste.

// Les serveurs sont chargés d'un coup (le maximum de l'API) : la recherche et la pagination de « Mes outils » se
// font dans l'interface. Au-delà de 100 serveurs visibles, il faudra les piloter côté serveur (`q`, `page`).
const SERVERS_PAGE_SIZE = 100;
const UNAVAILABLE_LABEL = "outil indisponible";

const internalTools = ref<Tool[]>([]);
const servers = ref<ToolServer[]>([]);
const loading = ref(false);
const error = ref("");
// Vrai une fois la liste connue : avant, on ne peut pas dire qu'un outil est indisponible.
const ready = ref(false);

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [internal, page] = await Promise.all([
      apiFetch<ToolOut[]>("/api/tools/internal"),
      apiFetch<Page<ToolServerOut>>(`/api/tool-servers?page_size=${SERVERS_PAGE_SIZE}`),
    ]);
    internalTools.value = internal.map(toTool);
    servers.value = page.items.map(toToolServer);
    ready.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Impossible de charger les outils.";
  } finally {
    loading.value = false;
  }
}

export function useTools() {
  /** Charge le registre une fois ; `force` le recharge (après un ajout, une suppression…). */
  const fetchTools = async (force = false) => {
    if (force || !ready.value) await load();
  };

  /** Liste les tools qu'un serveur expose, sans rien enregistrer. Lève `ApiError` (adresse refusée, serveur muet…). */
  async function discoverTools(draft: Pick<ToolServerDraft, "url" | "authMode" | "audience">): Promise<Tool[]> {
    const result = await apiFetch<{ tools: DiscoveredToolOut[] }>("/api/tool-servers/discover", {
      method: "POST",
      body: JSON.stringify({ url: draft.url.trim(), auth_mode: draft.authMode, audience: draft.audience.trim() || null }),
    });
    return result.tools.map(toPreviewTool);
  }

  async function addServer(draft: ToolServerDraft, selectedNames: string[]) {
    await apiFetch<ToolServerOut>("/api/tool-servers", {
      method: "POST",
      body: JSON.stringify({
        name: draft.name.trim(),
        url: draft.url.trim(),
        auth_mode: draft.authMode,
        audience: draft.audience.trim() || null,
        visibility: draft.visibility,
        tool_names: selectedNames,
      }),
    });
    await fetchTools(true);
  }

  async function refreshServer(id: string) {
    await apiFetch<ToolServerOut>(`/api/tool-servers/${id}/refresh`, { method: "POST" });
    await fetchTools(true);
  }

  async function removeServer(id: string) {
    await apiFetch(`/api/tool-servers/${id}`, { method: "DELETE" });
    await fetchTools(true);
  }

  /** Sélection d'un nouvel agent : les outils internes sont actifs par défaut. */
  const defaultToolIds = () => internalTools.value.map((tool) => tool.id);

  /** Les tools que l'on peut donner à un agent : les internes et ceux, autorisés, des serveurs MCP. */
  const allTools = () => [...internalTools.value, ...servers.value.flatMap((server) => server.tools.filter((tool) => tool.enabled))];

  /** Le nom lisible de chaque identifiant ; un outil qui n'est plus dans le registre est dit indisponible. */
  const toolNames = (ids: string[]) => {
    const byId = new Map(allTools().map((tool) => [tool.id, tool.name]));
    return ids.map((id) => byId.get(id) ?? (ready.value ? UNAVAILABLE_LABEL : id));
  };

  /** Un outil de l'agent que la personne ne peut plus utiliser (serveur supprimé, droit retiré, tool désautorisé). */
  const isUnavailable = (id: string) => ready.value && !allTools().some((tool) => tool.id === id);

  return {
    internalTools,
    servers,
    ready,
    loading,
    error,
    fetchTools,
    discoverTools,
    addServer,
    refreshServer,
    removeServer,
    defaultToolIds,
    allTools,
    toolNames,
    isUnavailable,
  };
}
