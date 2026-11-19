<script setup lang="ts">
/**
 * Pop-up de l'application : `DsfrModal` avec une fermeture au clic sur le fond qui ne se déclenche que si
 * l'appui et le relâchement ont eu lieu sur le fond (voir useBackdropClose). À utiliser à la place de `DsfrModal`.
 * Contournement d'un défaut de vue-dsfr : à supprimer quand DsfrModal sera corrigée.
 */
import type { DsfrModalProps } from "@gouvminint/vue-dsfr"; // à vérifier : sinon, importer depuis types/components/DsfrModal/DsfrModal.types

import { useBackdropClose } from "@/composables/useBackdropClose";

const props = defineProps<DsfrModalProps>();
const emit = defineEmits<{ close: [] }>();

// « Fond » = tout ce qui n'est pas le corps de la fenêtre (la règle de DsfrModal elle-même).
const backdrop = useBackdropClose(
  (event) => event.target instanceof Element && event.target.closest(".fr-modal__body") === null,
  () => {
    props.origin?.focus(); // DsfrModal le fait dans sa propre fermeture : on garde le retour du focus
    emit("close");
  },
);
</script>

<template>
  <!-- display: contents : aucune boîte ajoutée ; ce conteneur écoute seulement les événements qui remontent du <dialog>. -->
  <div class="app-modal" @pointerdown.capture="backdrop.onPointerdown" @pointerup="backdrop.onPointerup" @click="backdrop.onClick">
    <DsfrModal v-bind="props" disable-outside-interaction @close="emit('close')">
      <slot />
      <template v-if="$slots.footer" #footer><slot name="footer" /></template>
    </DsfrModal>
  </div>
</template>

<style scoped>
.app-modal {
  display: contents;
}
</style>
