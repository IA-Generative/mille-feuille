<script setup lang="ts">
import { computed, ref } from "vue";

import CapabilitiesCard from "@/components/admin/models/CapabilitiesCard.vue";
import CapabilityEditModal from "@/components/admin/models/CapabilityEditModal.vue";
import HubModelsPanel from "@/components/admin/models/HubModelsPanel.vue";
import ModelEditModal from "@/components/admin/models/ModelEditModal.vue";
import ModelRow from "@/components/admin/models/ModelRow.vue";
import ModelsModeCard from "@/components/admin/models/ModelsModeCard.vue";
import { useLlmModels } from "@/composables/useLlmModels";
import type { HubModel, LlmCapability } from "@/types/llmModel";

// Les modèles que l'application connaît et ce que l'administrateur dit qu'ils savent faire. Rien n'est déduit du
// hub : seuls ses noms sont lus, et la liste enregistrée sert de mémoire.
const {
  capabilities,
  models,
  hubModels,
  hubReadAt,
  hubError,
  mode,
  loading,
  error,
  defaultModelId,
  updateModel,
  move,
  removeModel,
  addModel,
  saveCapability,
  removeCapability,
  refreshHub,
  setMode,
  load,
} = useLlmModels();

const editedModelId = ref<string | null>(null);
const editedModel = computed(() => models.value.find((m) => m.id === editedModelId.value) ?? null);
const capabilitiesOf = (capabilityIds: string[]) => capabilities.value.filter((c) => capabilityIds.includes(c.id));

const capabilityOpened = ref(false);
const editedCapability = ref<LlmCapability | null>(null);
const refreshing = ref(false);

async function onSaveModel(capabilityIds: string[]) {
  if (editedModelId.value) await updateModel(editedModelId.value, { capabilityIds });
  editedModelId.value = null;
}

async function onRemoveModel() {
  if (!editedModelId.value) return;
  if (!confirm("Retirer ce modèle de la liste ? Il reste disponible sur le hub.")) return;
  await removeModel(editedModelId.value);
  editedModelId.value = null;
}

// Un modèle ajouté s'ouvre aussitôt : il n'a encore aucune capacité.
async function onAddModel(hub: HubModel) {
  editedModelId.value = await addModel(hub);
}

function openCapability(capability: LlmCapability | null) {
  editedCapability.value = capability;
  capabilityOpened.value = true;
}

async function onSaveCapability(input: { id?: string; name: string; description: string }) {
  await saveCapability(input);
  capabilityOpened.value = false;
}

async function onRemoveCapability() {
  if (!editedCapability.value) return;
  if (!confirm("Supprimer cette capacité ? Elle sera retirée de tous les modèles.")) return;
  await removeCapability(editedCapability.value.id);
  capabilityOpened.value = false;
}

async function onRefresh() {
  refreshing.value = true;
  try {
    await refreshHub();
  } finally {
    refreshing.value = false;
  }
}

defineExpose({ reload: load });
</script>

<template>
  <section class="admin-models">
    <h2 class="fr-h4">
      <VIcon name="ri-cpu-line" class="fr-mr-1w" />
      Modèles
    </h2>

    <div v-if="error" class="fr-alert fr-alert--error fr-alert--sm" role="alert">
      <p>{{ error }}</p>
    </div>
    <p v-if="loading && !models.length" class="fr-text--sm">Chargement…</p>

    <ModelsModeCard :mode="mode" @change="setMode" />

    <CapabilitiesCard :capabilities="capabilities" @add="openCapability(null)" @edit="openCapability" />

    <section class="admin-models__list" aria-labelledby="models-title">
      <h3 id="models-title" class="admin-models__title">Modèles enregistrés</h3>
      <ul class="admin-models__card">
        <ModelRow
          v-for="(model, index) in models"
          :key="model.id"
          :model="model"
          :capabilities="capabilitiesOf(model.capabilityIds)"
          :is-default="model.id === defaultModelId"
          :first="index === 0"
          :last="index === models.length - 1"
          @edit="editedModelId = model.id"
          @move="move(model.id, $event)"
          @toggle="updateModel(model.id, { enabled: $event })"
        />
      </ul>
    </section>

    <HubModelsPanel
      :models="hubModels"
      :read-at="hubReadAt"
      :error="hubError"
      :refreshing="refreshing"
      @add="onAddModel"
      @refresh="onRefresh"
    />

    <ModelEditModal
      :model="editedModel"
      :capabilities="capabilities"
      @close="editedModelId = null"
      @save="onSaveModel"
      @remove="onRemoveModel"
    />
    <CapabilityEditModal
      :opened="capabilityOpened"
      :capability="editedCapability"
      @close="capabilityOpened = false"
      @save="onSaveCapability"
      @remove="onRemoveCapability"
    />
  </section>
</template>

<style scoped>
.admin-models {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.admin-models h2 {
  margin: 0;
}

.admin-models__list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.admin-models__title {
  margin: 0;
  font-size: 1rem;
}

.admin-models__card {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--border-default-grey, #ddd);
  border-radius: 0.875rem;
  background: var(--background-default-grey, #fff);
}
</style>
