import { computed, reactive, type Ref } from "vue";

import type { Version } from "@/types/analyse";
import { apiFetch, userMessage } from "@/utils/api";

// Les questions fréquentes d'une analyse : chaque dossier en reçoit la réponse une fois analysé. Versionnées comme tout ce
// qui se modifie dans une analyse.

export interface AnalyseQuestions {
  questions: string[];
  versions: Version<{ questions: string[] }>[];
}

interface AnalyseQuestionsOut {
  questions: string[];
  versions: { id: string; created_at: string; content: { questions: string[] } }[];
}

interface State {
  data: AnalyseQuestions | null;
  loading: boolean;
  error: string;
}

const states = new Map<string, State>();

function stateFor(analyseId: string): State {
  let state = states.get(analyseId);
  if (!state) {
    state = reactive({ data: null, loading: false, error: "" });
    states.set(analyseId, state);
  }
  return state;
}

function toAnalyseQuestions(out: AnalyseQuestionsOut): AnalyseQuestions {
  return {
    questions: out.questions,
    versions: out.versions.map((v) => ({ id: v.id, createdAt: v.created_at, content: { questions: v.content.questions } })),
  };
}

export function useAnalyseQuestions(analyseId: Ref<string>) {
  const state = computed(() => stateFor(analyseId.value));
  const data = computed(() => state.value.data);
  const loading = computed(() => state.value.loading);
  const error = computed({ get: () => state.value.error, set: (value: string) => (state.value.error = value) });

  const url = (suffix = "") => `/api/analyses/${analyseId.value}/frequent-questions${suffix}`;

  async function load() {
    state.value.loading = true;
    error.value = "";
    try {
      state.value.data = toAnalyseQuestions(await apiFetch<AnalyseQuestionsOut>(url()));
    } catch (e) {
      error.value = userMessage(e, "Impossible de charger les questions fréquentes.");
    } finally {
      state.value.loading = false;
    }
  }

  /** Remplace la liste. Vrai si c'est fait ; sinon `error` dit pourquoi. */
  async function save(questions: string[]): Promise<boolean> {
    error.value = "";
    try {
      const body = JSON.stringify({ questions });
      state.value.data = toAnalyseQuestions(await apiFetch<AnalyseQuestionsOut>(url(), { method: "PUT", body }));
      return true;
    } catch (e) {
      error.value = userMessage(e, "Impossible d'enregistrer ces questions.");
      return false;
    }
  }

  async function restore(versionId: string): Promise<boolean> {
    error.value = "";
    try {
      state.value.data = toAnalyseQuestions(
        await apiFetch<AnalyseQuestionsOut>(url(`/restore/${versionId}`), { method: "POST" }),
      );
      return true;
    } catch (e) {
      error.value = userMessage(e, "Impossible de restaurer cette version.");
      return false;
    }
  }

  return { data, loading, error, load, save, restore };
}
