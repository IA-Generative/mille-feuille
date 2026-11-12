<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import DueSettingsEditor from "@/components/analyses/DueSettingsEditor.vue";
import StatusesEditor from "@/components/statuses/StatusesEditor.vue";
import StatusReplacementModal from "@/components/statuses/StatusReplacementModal.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import type { DueSettings, StatusDraft } from "@/types/analyse";
import { ApiError, userMessage } from "@/utils/api";

// Onglet « Statuts et échéance » d'une analyse : les statuts que peuvent prendre ses dossiers (#170), puis leur
// échéance (#172). Supprimer un statut encore utilisé demande un remplaçant.
const route = useRoute();
const { getById, fetchAnalyse, updateStatuses, restoreStatusesVersion, updateDueSettings, restoreDueSettingsVersion } =
  useAnalyses();

const analyse = computed(() => getById(String(route.params.id)));
onMounted(() => {
  if (!analyse.value) fetchAnalyse(String(route.params.id));
});

interface InUse {
  id: string;
  name: string;
  dossierCount: number;
}

const saving = ref(false);
const message = ref("");
const error = ref("");
/** Opération en attente d'un statut de remplacement (409 du serveur). */
const pending = ref<{ inUse: InUse[]; retry: (replacements: Record<string, string>) => Promise<void> } | null>(null);

const candidates = computed(() => {
  const removed = new Set(pending.value?.inUse.map((s) => s.id));
  return (analyse.value?.statuses ?? []).filter((s) => !removed.has(s.id)).map((s) => ({ id: s.id, name: s.name }));
});

/** Exécute une modification ; sur 409, ouvre le choix des remplaçants puis réessaie avec eux. */
async function run(operation: (replacements: Record<string, string>) => Promise<void>, successMessage: string) {
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    await operation({});
    message.value = successMessage;
  } catch (e) {
    const detail = e instanceof ApiError ? (e.detail as any) : null;
    if (e instanceof ApiError && e.status === 409 && detail?.code === "status_in_use") {
      pending.value = {
        inUse: detail.statuses.map((s: any) => ({ id: s.id, name: s.name, dossierCount: s.dossier_count })),
        retry: async (replacements) => {
          await operation(replacements);
          message.value = successMessage;
        },
      };
    } else {
      error.value = userMessage(e, "L'enregistrement a échoué.");
    }
  } finally {
    saving.value = false;
  }
}

function onSave(drafts: StatusDraft[]) {
  run((replacements) => updateStatuses(analyse.value!.id, drafts, replacements), "Statuts enregistrés. L'ancienne liste est dans l'historique.");
}

function onRestore(versionId: string) {
  run((replacements) => restoreStatusesVersion(analyse.value!.id, versionId, replacements), "Version restaurée.");
}

function onSaveDue(settings: DueSettings) {
  run(() => updateDueSettings(analyse.value!.id, settings), "Échéance enregistrée. L'ancien réglage est dans l'historique.");
}

function onRestoreDue(versionId: string) {
  run(() => restoreDueSettingsVersion(analyse.value!.id, versionId), "Version restaurée.");
}

async function confirmReplacement(replacements: Record<string, string>) {
  const current = pending.value;
  pending.value = null;
  if (!current) return;
  saving.value = true;
  try {
    await current.retry(replacements);
  } catch (e) {
    error.value = userMessage(e, "L'enregistrement a échoué.");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div v-if="analyse">
    <StatusesEditor
      :statuses="analyse.statuses"
      :versions="analyse.statusesVersions"
      :saving="saving"
      @save="onSave"
      @restore="onRestore"
    />
    <hr class="analyse-statuses__sep" />
    <DueSettingsEditor
      :settings="analyse.dueSettings"
      :versions="analyse.dueSettingsVersions"
      :saving="saving"
      @save="onSaveDue"
      @restore="onRestoreDue"
    />
    <p v-if="message" class="analyse-statuses__ok" role="status">{{ message }}</p>
    <p v-if="error" class="analyse-statuses__error" role="alert">{{ error }}</p>

    <StatusReplacementModal
      v-if="pending"
      :in-use="pending.inUse"
      :candidates="candidates"
      @confirm="confirmReplacement"
      @cancel="pending = null"
    />
  </div>
  <div v-else>
    <p>Chargement…</p>
  </div>
</template>

<style scoped>
.analyse-statuses__sep {
  margin: 2rem 0;
}

.analyse-statuses__ok {
  margin: 0.75rem 0 0;
  color: var(--text-default-success);
}

.analyse-statuses__error {
  margin: 0.75rem 0 0;
  color: var(--text-default-error);
}
</style>
