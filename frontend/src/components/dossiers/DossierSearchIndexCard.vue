<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, toRef } from "vue";

import { useDossierSearchIndex } from "@/composables/useDossierSearchIndex";

// L'index de recherche du dossier, en une phrase. Les actions ne se montrent que quand il y a quelque chose à faire :
// reconstruire (index obsolète ou en erreur), puis valider la bascule ou revenir à l'ancien index.
const props = defineProps<{ dossierId: string }>();
const { index, error, load, rebuild, validate, rollback } = useDossierSearchIndex(toRef(props, "dossierId"));

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  load();
  poll = setInterval(() => {
    if (index.value?.rebuild && ["queued", "building"].includes(index.value.rebuild.status)) load();
  }, 4_000);
});
onBeforeUnmount(() => clearInterval(poll));

const rebuildStatus = computed(() => index.value?.rebuild?.status);
const active = computed(() => rebuildStatus.value === "queued" || rebuildStatus.value === "building");

const text = computed(() => {
  const i = index.value;
  if (!i) return "";
  const r = i.rebuild;
  if (r?.status === "queued") return "Reconstruction de l'index en attente de son tour.";
  if (r?.status === "building") {
    const progress = r.totalPages ? ` (${r.donePages} page${r.donePages > 1 ? "s" : ""} sur ${r.totalPages})` : "";
    return `Reconstruction de l'index en cours${progress}. L'index actuel continue de répondre.`;
  }
  if (r?.status === "swapped") return "Le nouvel index est en service. Validez-le pour supprimer l'ancien, ou revenez à l'ancien.";
  if (r?.status === "failed") return `La dernière reconstruction a échoué${r.error ? ` : ${r.error}` : ""}. L'index actuel est inchangé.`;
  if (i.freshness === "none") return i.problem ?? "Ce dossier n'est pas encore indexé pour la recherche.";
  if (i.status === "error") return `L'indexation a échoué${i.error ? ` : ${i.error}` : ""}.`;
  if (i.status === "indexing") return "Indexation en cours.";
  if (i.freshness === "obsolete") return "L'index a été construit avec d'autres réglages que ceux de l'analyse.";
  return `Recherche à jour (${i.chunkCount} passage${i.chunkCount > 1 ? "s" : ""}).`;
});

const canRebuild = computed(() => {
  const i = index.value;
  return !!i && !active.value && rebuildStatus.value !== "swapped" && (i.freshness === "obsolete" || i.status === "error" || i.freshness === "none");
});
</script>

<template>
  <section v-if="index" class="dsi" aria-label="Recherche dans le dossier">
    <p class="fr-text--sm dsi__text" aria-live="polite">{{ text }}</p>
    <div class="dsi__actions">
      <DsfrButton v-if="canRebuild" :label="index.freshness === 'none' ? 'Indexer' : 'Reconstruire'" icon="ri-refresh-line" secondary size="sm" @click="rebuild" />
      <template v-if="rebuildStatus === 'swapped' && index.rebuild">
        <DsfrButton label="Valider" size="sm" @click="validate(index.rebuild.id)" />
        <DsfrButton label="Revenir à l'ancien" tertiary size="sm" @click="rollback(index.rebuild.id)" />
      </template>
      <DsfrButton v-if="active && index.rebuild" label="Annuler" tertiary size="sm" @click="rollback(index.rebuild.id)" />
    </div>
    <p v-if="error" class="fr-text--sm dsi__error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.dsi {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 1.5rem;
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
}

.dsi__text,
.dsi__error {
  margin: 0;
}

.dsi__error {
  flex-basis: 100%;
  color: var(--text-default-error);
}

.dsi__actions {
  display: flex;
  gap: 0.5rem;
}
</style>
