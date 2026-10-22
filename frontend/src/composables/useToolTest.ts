import type { Tool, ToolTestRun } from "@/types/tool";

// Test unitaire d'un tool (phase 5 du plan, docs/tools-mcp-plan.md) : SIMULÉ. Le vrai passera par le backend, avec
// l'identité de la personne, en réutilisant le proxy d'appel avec une liste réduite à ce seul tool.

/** Demandes d'exemple : l'identifiant pour un tool interne, le nom pour un tool MCP. */
const EXAMPLE_PROMPTS: Record<string, string> = {
  recherche_dossier: "Cherche où il est question du RIB dans le dossier.",
  calcul_dates: "Quelle est la date 30 jours après le 3 mars 2026 ?",
  notes_internes: "Ajoute une note : RIB à redemander à l'association.",
  rechercher_texte: "Cherche les textes de loi sur les subventions aux associations.",
  lire_article: "Lis l'article L1111-1.",
  envoyer_courriel: "Écris au service des subventions pour réclamer le RIB.",
};

export const examplePromptOf = (tool: Tool) =>
  EXAMPLE_PROMPTS[tool.kind === "internal" ? tool.id : tool.name] ?? `Utilise l'outil « ${tool.name} » sur un exemple simple.`;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Le modèle ne dispose que de ce tool et choisit ses arguments ; on ne renvoie que la sortie brute du tool. */
export async function runToolTest(tool: Tool, prompt: string): Promise<ToolTestRun> {
  const request = { method: "tools/call", params: { name: tool.name, arguments: { requete: prompt } } };
  const startedAt = Date.now();
  await wait(700);
  const durationMs = Date.now() - startedAt;
  if (prompt.includes("999")) {
    return { ok: false, durationMs, request, output: { code: "introuvable", message: "Aucun résultat pour cette valeur." } };
  }
  return {
    ok: true,
    durationMs,
    request,
    output: tool.sideEffect
      ? { ok: true, message: "Action effectuée.", reference: "REF-2026-0412" }
      : { ok: true, resultats: [{ titre: "Résultat 1", extrait: "…" }, { titre: "Résultat 2", extrait: "…" }], total: 2 },
  };
}
