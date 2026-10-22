<script setup lang="ts">
import { ref, watch } from "vue";

import ToolPicker from "@/components/tools/ToolPicker.vue";

const opened = defineModel<boolean>("opened", { default: false });
const props = defineProps<{ toolIds: string[] }>();
const emit = defineEmits<{ confirm: [toolIds: string[]] }>();

// Brouillon : la sélection n'est appliquée qu'à la validation.
const draft = ref<string[]>([...props.toolIds]);

watch(opened, (isOpened) => {
  if (isOpened) draft.value = [...props.toolIds];
});

function confirm() {
  emit("confirm", draft.value);
  opened.value = false;
}
</script>

<template>
  <!-- Téléportée : une carte parente avec un transform enfermerait sinon la modale (position: fixed). -->
  <Teleport to="body">
  <DsfrModal
    :opened="opened"
    title="Choisir les outils de l'agent"
    size="lg"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: `Valider (${draft.length})`, onClick: confirm },
    ]"
    @close="opened = false"
  >
    <ToolPicker v-model="draft" />
  </DsfrModal>
  </Teleport>
</template>
