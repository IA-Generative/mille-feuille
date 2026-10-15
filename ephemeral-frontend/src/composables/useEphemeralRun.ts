import { computed, onBeforeUnmount, ref } from "vue";

import { apiFetch } from "@/api";
import {
  TERMINAL,
  type ClassificationOut,
  type EntityDef,
  type ExtractionOut,
  type LabelDef,
  type Mode,
  type RunOut,
} from "@/types";

const POLL_MS = 2000;

export interface RunRequest {
  mode: Mode;
  file: File;
  ttlHours: number;
  persist: boolean;
  classificationPrompt: string;
  extractionPrompt: string;
  multiLabel: boolean;
  labels: LabelDef[];
  entities: EntityDef[];
}

export function useEphemeralRun() {
  // Un run « both » a deux résultats lus avec le même id ; le statut, l'erreur et l'expiration sont ceux du run.
  const classification = ref<ClassificationOut | null>(null);
  const extraction = ref<ExtractionOut | null>(null);
  const result = computed<RunOut | null>(() => extraction.value ?? classification.value);
  const runId = ref<string | null>(null);
  const mode = ref<Mode>("classification");
  const submitting = ref(false);
  const error = ref("");
  let timer: ReturnType<typeof setTimeout> | null = null;

  const clearResults = () => {
    classification.value = null;
    extraction.value = null;
  };

  const stopPolling = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };

  const poll = async () => {
    if (!runId.value) return;
    try {
      const [wantClassification, wantExtraction] = [mode.value !== "extraction", mode.value !== "classification"];
      const [classified, extracted] = await Promise.all([
        wantClassification ? apiFetch<ClassificationOut>(`/api/ephemeral/classifications/${runId.value}`) : null,
        wantExtraction ? apiFetch<ExtractionOut>(`/api/ephemeral/extractions/${runId.value}`) : null,
      ]);
      classification.value = classified;
      extraction.value = extracted;
      const status = (extracted ?? classified)!.status;
      if (!TERMINAL.includes(status)) timer = setTimeout(poll, POLL_MS);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Erreur inconnue";
    }
  };

  const start = async (request: RunRequest) => {
    stopPolling();
    error.value = "";
    clearResults();
    submitting.value = true;
    try {
      const form = new FormData();
      form.append("file", request.file);
      form.append("persist", String(request.persist));
      if (request.mode !== "extraction") {
        form.append("labels", JSON.stringify(request.labels));
        form.append("multi_label", String(request.multiLabel));
        if (request.classificationPrompt) form.append("classification_prompt", request.classificationPrompt);
      }
      if (request.mode !== "classification") {
        form.append("entities", JSON.stringify(request.entities));
        if (request.extractionPrompt) form.append("extraction_prompt", request.extractionPrompt);
      }
      const route = request.mode === "both" ? "classification-and-extraction" : `${request.mode}s`;
      const created = await apiFetch<{ run_id: string }>(
        `/api/ephemeral/${route}?ttl_hours=${request.ttlHours}`,
        { method: "POST", body: form },
      );
      mode.value = request.mode;
      runId.value = created.run_id;
      await poll();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Erreur inconnue";
    } finally {
      submitting.value = false;
    }
  };

  /** Rouvre un run existant (depuis « Mes tâches »). */
  const open = async (id: string, kind: Mode) => {
    stopPolling();
    error.value = "";
    clearResults();
    mode.value = kind;
    runId.value = id;
    await poll();
  };

  const close = () => {
    stopPolling();
    runId.value = null;
    clearResults();
  };

  const stop = async () => {
    if (!runId.value) return;
    await apiFetch(`/api/ephemeral/runs/${runId.value}/stop`, { method: "POST" });
    stopPolling();
    await poll();
  };

  onBeforeUnmount(stopPolling);
  return { result, classification, extraction, runId, mode, submitting, error, start, open, close, stop };
}
