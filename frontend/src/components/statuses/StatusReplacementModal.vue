<script setup lang="ts">
import { computed, ref } from "vue";

import AppModal from "@/components/AppModal.vue";
// Un statut supprimé est encore utilisé par des dossiers : on choisit, pour
// chacun, le statut qui reprend ses dossiers (le serveur répond 409 sinon).
const props = defineProps<{
  /** Statuts supprimés encore utilisés, avec le nombre de dossiers concernés. */
  inUse: { id: string; name: string; dossierCount: number }[];
  /** Statuts conservés pouvant servir de remplaçant. */
  candidates: { id: string; name: string }[];
}>();
const emit = defineEmits<{ confirm: [replacements: Record<string, string>]; cancel: [] }>();

const choice = ref<Record<string, string>>(Object.fromEntries(props.inUse.map((s) => [s.id, ""])));
const complete = computed(() => props.inUse.every((s) => choice.value[s.id]));

const actions = computed(() => [
  { label: "Remplacer et enregistrer", disabled: !complete.value, onClick: () => emit("confirm", { ...choice.value }) },
  { label: "Annuler", secondary: true, onClick: () => emit("cancel") },
]);
</script>

<template>
  <AppModal :opened="true" title="Des dossiers utilisent ces statuts" icon="ri-flag-line" :actions="actions" @close="emit('cancel')">
    <p>Choisissez le statut qui reprendra les dossiers de chaque statut supprimé. Le changement est enregistré dans l'historique des statuts.</p>
    <div v-for="s in inUse" :key="s.id" class="srm__row">
      <label :for="`srm-${s.id}`">
        <strong>{{ s.name }}</strong> — {{ s.dossierCount }} dossier{{ s.dossierCount > 1 ? "s" : "" }}, reprendre par :
      </label>
      <select :id="`srm-${s.id}`" v-model="choice[s.id]" class="fr-select">
        <option value="" disabled>Choisir un statut…</option>
        <option v-for="c in candidates" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </div>
  </AppModal>
</template>

<style scoped>
.srm__row {
  margin-bottom: 1rem;
}

.srm__row label {
  display: block;
  margin-bottom: 0.25rem;
}
</style>
