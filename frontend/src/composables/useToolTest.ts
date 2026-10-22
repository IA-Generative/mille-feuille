import type { Tool, ToolTestRun } from "@/types/tool";
import { apiFetch } from "@/utils/api";

// Test unitaire d'un tool MCP : une demande en langage naturel, un modèle qui n'a que ce tool et choisit ses
// arguments, l'appel par le backend avec l'identité de la personne. On n'affiche que la sortie brute.

interface ToolTestOut {
  ok: boolean;
  code: string | null;
  output: string;
  truncated: boolean;
  duration_ms: number;
  model: string | null;
  call: { name: string; arguments: Record<string, unknown> } | null;
}

export const examplePromptOf = (tool: Tool) => `Utilise l'outil « ${tool.name} » sur un exemple simple.`;

export interface ToolTestOptions {
  /** Identifiant de modèle (voir GET /api/models) ; vide = le modèle par défaut du hub. */
  model: string;
  /** Obligatoire pour un tool qui modifie des données : le test l'exécute pour de vrai. */
  confirmed: boolean;
}

export async function runToolTest(tool: Tool, prompt: string, options: ToolTestOptions): Promise<ToolTestRun> {
  const raw = await apiFetch<ToolTestOut>(`/api/tools/${tool.id}/test`, {
    method: "POST",
    body: JSON.stringify({ prompt, model: options.model || null, confirmed: options.confirmed }),
  });
  return {
    ok: raw.ok,
    code: raw.code,
    output: raw.output,
    truncated: raw.truncated,
    durationMs: raw.duration_ms,
    model: raw.model,
    call: raw.call,
  };
}
