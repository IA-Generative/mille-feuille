// Aides LLM ("Aide à la rédaction...") : chaque fonction construit un
// prompt d'instruction et l'envoie à POST /api/llm/complete (voir
// useLlmComplete.ts). `model` vient du LlmAssistButton qui a déclenché
// l'appel (null = modèle par défaut du hub côté backend).
import { completeChat, parseJsonFromCompletion } from "@/composables/useLlmComplete";
import type { EntityDefinition, EntityType, LabelDefinition } from "@/types/analyse";

export const MIN_ASSIST_WORDS = 3;

/** L'aide LLM n'est utile qu'à partir de quelques mots : en dessous, elle invente plus qu'elle n'améliore. */
export function hasEnoughWords(text: string): boolean {
  return text.trim().split(/\s+/).filter(Boolean).length >= MIN_ASSIST_WORDS;
}

export const ASSIST_MIN_WORDS_HINT = `Saisissez au moins ${MIN_ASSIST_WORDS} mots pour utiliser l'aide LLM.`;

export async function suggestClassificationPrompt(draft: string = "", model: string | null = null): Promise<string> {
  const context = draft.trim()
    ? `L'utilisateur a déjà commencé à rédiger ce prompt ou décrit son besoin : "${draft.trim()}". Prends-le en ` +
      "compte pour l'améliorer ou le compléter. "
    : "";
  return completeChat(
    context +
      "Rédige, en français, un prompt d'instruction destiné à un modèle de langage chargé de classifier des " +
      "documents administratifs. Le prompt doit lui demander de choisir un label parmi une liste fournie et de " +
      "retourner sa décision avec un score de confiance. Réponds uniquement avec le texte du prompt, sans " +
      "balises ni explication.",
    model,
  );
}

export async function suggestExtractionPrompt(draft: string = "", model: string | null = null): Promise<string> {
  const context = draft.trim()
    ? `L'utilisateur a déjà commencé à rédiger ce prompt ou décrit son besoin : "${draft.trim()}". Prends-le en ` +
      "compte pour l'améliorer ou le compléter. "
    : "";
  return completeChat(
    context +
      "Rédige, en français, un prompt d'instruction destiné à un modèle de langage chargé d'extraire des entités " +
      "nommées d'un document administratif, au format JSON strict, sans inventer de champ absent du document. " +
      "Réponds uniquement avec le texte du prompt, sans balises ni explication.",
    model,
  );
}

export async function suggestAgentPrompt(draft: string = "", model: string | null = null): Promise<string> {
  const instruction = draft.trim()
    ? `L'utilisateur décrit ainsi le but de l'agent : "${draft.trim()}". À partir de cette description, rédige, ` +
      "en français, un prompt décrivant précisément le but métier d'un agent d'analyse de dossier " +
      "administratif (par exemple : contrôle de cohérence entre pièces, rédaction d'une synthèse, construction " +
      "d'une timeline des événements du dossier...) et le résultat attendu. Réponds uniquement avec le texte du " +
      "prompt, sans balises ni explication."
    : "Rédige, en français, un prompt décrivant précisément le but métier d'un agent d'analyse de dossier " +
      "administratif (par exemple : contrôle de cohérence entre pièces, rédaction d'une synthèse, construction " +
      "d'une timeline des événements du dossier...) et le résultat attendu. Réponds uniquement avec le texte du " +
      "prompt, sans balises ni explication.";
  return completeChat(instruction, model);
}

export async function suggestAnalyseDescription(
  draft: string = "",
  model: string | null = null,
): Promise<string> {
  const instruction = draft.trim()
    ? `L'utilisateur décrit ainsi le but de l'analyse : "${draft.trim()}". À partir de cette description, rédige, ` +
      "en français, une description structurée et complète de l'analyse de dossier administratif. La description doit " +
      "préciser : le contexte, l'objectif métier, les types de documents concernés, et le résultat attendu. " +
      "Réponds uniquement avec le texte de la description, sans balises ni explication."
    : "Rédige, en français, une description structurée pour une analyse de dossier administratif. La description doit " +
      "préciser : le contexte, l'objectif métier, les types de documents concernés, et le résultat attendu. " +
      "Réponds uniquement avec le texte de la description, sans balises ni explication.";
  return completeChat(instruction, model);
}

export async function suggestLabels(model: string | null = null): Promise<Omit<LabelDefinition, "id">[]> {
  const content = await completeChat(
    "Propose une liste de labels de classification pour des documents administratifs français (pièces " +
      "justificatives : carte d'identité, passeport, justificatif de domicile, avis d'imposition...). Réponds " +
      'uniquement avec un JSON strict de la forme [{"name": "...", "definition": "..."}], sans balises ni ' +
      "explication.",
    model,
  );
  return parseJsonFromCompletion<Omit<LabelDefinition, "id">[]>(content);
}

export async function suggestEntities(model: string | null = null): Promise<Omit<EntityDefinition, "id">[]> {
  const content = await completeChat(
    "Propose une liste d'entités à extraire de documents administratifs français (nom, prénom, date de " +
      "naissance, adresse postale, numéro de pièce...). Réponds uniquement avec un JSON strict de la forme " +
      '[{"name": "...", "definition": "...", "type": "texte"|"date"|"nombre"|"booléen"|"identifiant"}], sans ' +
      "balises ni explication.",
    model,
  );
  return parseJsonFromCompletion<Omit<EntityDefinition, "id">[]>(content);
}

export async function suggestLabelDefinition(name: string, model: string | null = null): Promise<string> {
  return completeChat(
    `Rédige, en français, une définition concise (une phrase) pour le label de classification "${name}" ` +
      "utilisé pour catégoriser des documents administratifs. Réponds uniquement avec le texte de la " +
      "définition, sans balises ni explication.",
    model,
  );
}

export async function suggestEntityDefinition(
  name: string,
  model: string | null = null,
): Promise<{ definition: string; type: EntityType }> {
  const content = await completeChat(
    `Propose, en français, une définition concise et un type pour l'entité "${name}" à extraire de documents ` +
      'administratifs. Réponds uniquement avec un JSON strict de la forme {"definition": "...", "type": ' +
      '"texte"|"date"|"nombre"|"booléen"|"identifiant"}, sans balises ni explication.',
    model,
  );
  return parseJsonFromCompletion<{ definition: string; type: EntityType }>(content);
}

// --- Modèles de document (administration, issue #139) ---

function withDraft(draft: string, what: string): string {
  return draft.trim()
    ? `L'utilisateur a déjà commencé à rédiger ${what} ou décrit son besoin : "${draft.trim()}". Prends-le en ` +
        "compte pour l'améliorer ou le compléter. "
    : "";
}

export async function suggestTemplateDescription(
  draft: string,
  ctx: { name: string },
  model: string | null = null,
): Promise<string> {
  return completeChat(
    withDraft(draft, "cette description") +
      `Rédige, en français, une description courte (deux ou trois phrases) du modèle de document « ${ctx.name || "sans nom"} », ` +
      "utilisé pour produire un document de fin d'instruction d'un dossier administratif : à quoi il sert et dans quel cas " +
      "l'utiliser. Réponds uniquement avec le texte de la description, sans balises ni explication.",
    model,
  );
}

export async function suggestTemplateInstructions(
  draft: string,
  ctx: { name: string; description: string },
  model: string | null = null,
): Promise<string> {
  return completeChat(
    withDraft(draft, "ces consignes") +
      "Rédige, en français, des consignes générales de rédaction destinées à un agent qui propose les valeurs des champs " +
      `du modèle de document « ${ctx.name || "sans nom"} »` +
      (ctx.description.trim() ? ` (${ctx.description.trim()})` : "") +
      " : ton, registre administratif, vouvoiement, formules à privilégier ou à éviter. Quelques lignes, sans inventer " +
      "d'information sur un dossier. Réponds uniquement avec le texte des consignes, sans balises ni explication.",
    model,
  );
}

export async function suggestFieldInstruction(
  draft: string,
  ctx: { templateName: string; label: string; name: string; type: string; source: string },
  model: string | null = null,
): Promise<string> {
  return completeChat(
    withDraft(draft, "cette consigne") +
      "Rédige, en français, une consigne courte (une ou deux phrases) pour l'agent qui propose la valeur du champ " +
      `« ${ctx.label || ctx.name} » (nom ${ctx.name}, type ${ctx.type}) du modèle de document « ${ctx.templateName || "sans nom"} ». ` +
      `La valeur ${ctx.source}. Précise le format attendu (par exemple une date au format JJ/MM/AAAA), la longueur et le ton ` +
      "si cela a un sens pour ce champ. Ne donne pas d'exemple de valeur inventée. Réponds uniquement avec le texte de la " +
      "consigne, sans balises ni explication.",
    model,
  );
}
