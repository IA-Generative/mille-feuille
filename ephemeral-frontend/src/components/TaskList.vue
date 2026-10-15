<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

import { apiFetch } from "@/api";
import { TERMINAL, type Mode, type RunSummary } from "@/types";

const emit = defineEmits<{ open: [id: string, kind: Mode] }>();

const runs = ref<RunSummary[]>([]);
const loading = ref(true);
const error = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;

const KIND: Record<string, string> = {
  classification: "Classification",
  extraction: "Extraction",
  both: "Classification et extraction",
  analyse: "Analyse",
};
const BADGE: Record<string, string> = {
  "terminé": "fr-badge--success",
  "échec": "fr-badge--error",
  "arrêté": "fr-badge--warning",
};
const date = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });

const load = async () => {
  try {
    runs.value = await apiFetch<RunSummary[]>("/api/ephemeral/runs");
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Erreur inconnue";
  } finally {
    loading.value = false;
  }
  // Tant qu'un run tourne, on rafraîchit la liste.
  if (runs.value.some((run) => !TERMINAL.includes(run.status))) timer = setTimeout(load, 3000);
};

const remove = async (run: RunSummary) => {
  await apiFetch(`/api/ephemeral/runs/${run.id}`, { method: "DELETE" });
  runs.value = runs.value.filter((r) => r.id !== run.id);
};

onMounted(load);
onBeforeUnmount(() => timer && clearTimeout(timer));
</script>

<template>
  <p v-if="loading" class="fr-text--sm">Chargement…</p>
  <p v-else-if="error" class="fr-error-text">{{ error }}</p>
  <p v-else-if="!runs.length" class="fr-text--lead muted">Aucune tâche pour l'instant.</p>
  <ul v-else class="tasks">
    <li v-for="run in runs" :key="run.id" class="task">
      <button
        class="main"
        :disabled="run.kind === 'analyse'"
        :title="run.kind === 'analyse' ? 'Visible via l\'API' : 'Voir le résultat'"
        @click="emit('open', run.id, run.kind as Mode)"
      >
        <strong>{{ run.documents[0] ?? "Document" }}</strong>
        <span class="fr-text--sm muted">
          {{ KIND[run.kind] }} · {{ date(run.created_at) }}
          <template v-if="run.persist"> · conservé</template>
          <template v-else-if="run.expires_at"> · supprimé le {{ date(run.expires_at) }}</template>
        </span>
      </button>
      <span class="fr-badge fr-badge--sm" :class="BADGE[run.status] ?? 'fr-badge--info'">{{ run.status }}</span>
      <button class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-delete-line" title="Supprimer" @click="remove(run)">
        Supprimer
      </button>
    </li>
  </ul>
</template>

<style scoped>
.tasks {
  list-style: none;
  padding: 0;
  margin: 0;
}
.task {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--border-default-grey);
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  color: inherit;
}
.main:disabled {
  cursor: default;
}
.muted {
  color: var(--text-mention-grey);
}
</style>
