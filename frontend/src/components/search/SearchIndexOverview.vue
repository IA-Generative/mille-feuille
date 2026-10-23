<script setup lang="ts">
import { computed } from "vue";

import type { IndexOverview } from "@/types/search";

// Où en sont les index de recherche des dossiers de l'analyse. Une seule phrase par état, jamais de couleur seule :
// ce qui est à faire (reconstruire) est le seul bouton.
const props = defineProps<{ overview: IndexOverview; busy?: boolean }>();
const emit = defineEmits<{ rebuild: [] }>();

const toRebuild = computed(() => props.overview.obsolete + props.overview.errors);
const waiting = computed(() => props.overview.rebuilding + props.overview.queued);

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const lines = computed(() => {
  const o = props.overview;
  const list = [`${plural(o.indexed, "dossier indexé", "dossiers indexés")} sur ${o.dossiers}`];
  if (o.obsolete) list.push(`${plural(o.obsolete, "construit", "construits")} avec d'autres réglages`);
  if (o.errors) list.push(`${plural(o.errors, "en erreur", "en erreur")}`);
  if (o.rebuilding) list.push(`${plural(o.rebuilding, "en cours de reconstruction", "en cours de reconstruction")}`);
  if (o.queued) list.push(`${plural(o.queued, "en attente", "en attente")}`);
  if (o.toValidate) list.push(`${plural(o.toValidate, "à valider", "à valider")} (ouvrez le dossier)`);
  return list;
});
</script>

<template>
  <div class="sio">
    <p class="fr-text--sm sio__text" aria-live="polite">{{ lines.join(" · ") }}</p>
    <DsfrButton
      v-if="toRebuild > 0 && waiting === 0"
      label="Reconstruire les index"
      icon="ri-refresh-line"
      secondary
      size="sm"
      :disabled="busy"
      @click="emit('rebuild')"
    />
  </div>
</template>

<style scoped>
.sio {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
  border-radius: 0.75rem;
  background: var(--background-alt-grey);
}

.sio__text {
  margin: 0;
}
</style>
