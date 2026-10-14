import { onBeforeUnmount, ref } from "vue";

import { apiFetch } from "@/api";
import { TERMINAL, type EntityDef, type LabelDef, type Mode, type RunOut } from "@/types";

const POLL_MS = 2000;

export interface RunRequest {
  mode: Mode;
  file: File;
  ttlHours: number;
  persist: boolean;
  prompt: string;
  multiLabel: boolean;
  labels: LabelDef[];
  entities: EntityDef[];
}

export function useEphemeralRun() {
  const result = ref<RunOut | null>(null);
  const runId = ref<string | null>(null);
  const mode = ref<Mode>("classification");
  const submitting = ref(false);
  const error = ref("");
  let timer: ReturnType<typeof setTimeout> | null = null;

  const stopPolling = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };

  const poll = async () => {
    if (!runId.value) return;
    try {
      const out = await apiFetch<RunOut>(`/api/ephemeral/${mode.value}s/${runId.value}`);
      result.value = out;
      if (!TERMINAL.includes(out.status)) timer = setTimeout(poll, POLL_MS);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Erreur inconnue";
    }
  };

  const start = async (request: RunRequest) => {
    stopPolling();
    error.value = "";
    result.value = null;
    submitting.value = true;
    try {
      const form = new FormData();
      form.append("file", request.file);
      form.append("persist", String(request.persist));
      if (request.mode === "classification") {
        form.append("labels", JSON.stringify(request.labels));
        form.append("multi_label", String(request.multiLabel));
        if (request.prompt) form.append("classification_prompt", request.prompt);
      } else {
        form.append("entities", JSON.stringify(request.entities));
        if (request.prompt) form.append("extraction_prompt", request.prompt);
      }
      const created = await apiFetch<{ run_id: string }>(
        `/api/ephemeral/${request.mode}s?ttl_hours=${request.ttlHours}`,
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
    result.value = null;
    mode.value = kind;
    runId.value = id;
    await poll();
  };

  const close = () => {
    stopPolling();
    runId.value = null;
    result.value = null;
  };

  const stop = async () => {
    if (!runId.value) return;
    await apiFetch(`/api/ephemeral/runs/${runId.value}/stop`, { method: "POST" });
    stopPolling();
    await poll();
  };

  onBeforeUnmount(stopPolling);
  return { result, runId, mode, submitting, error, start, open, close, stop };
}
