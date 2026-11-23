<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, useTemplateRef, watch } from "vue";
/**
 * Pop-up de l'application : `DsfrModal` avec une fermeture au clic sur le fond qui ne se déclenche que si
 * l'appui et le relâchement ont eu lieu sur le fond (voir useBackdropClose). À utiliser à la place de `DsfrModal`.
 * Contournement d'un défaut de vue-dsfr : à supprimer quand DsfrModal sera corrigée.
 */
import type { DsfrModalProps } from "@gouvminint/vue-dsfr"; // à vérifier : sinon, importer depuis types/components/DsfrModal/DsfrModal.types

import { useBackdropClose } from "@/composables/useBackdropClose";

const props = withDefaults(defineProps<DsfrModalProps & { closeOnBackdrop?: boolean }>(), { closeOnBackdrop: true });
const emit = defineEmits<{ close: [] }>();

// `closeOnBackdrop` est propre à AppModal : on ne le transmet pas à DsfrModal.
const modalProps = computed(() => {
  const { closeOnBackdrop: _ignored, ...rest } = props;
  return rest;
});

// « Fond » = tout ce qui n'est pas le corps de la fenêtre (la règle de DsfrModal elle-même).
const backdrop = useBackdropClose(
  (event) => event.target instanceof Element && event.target.closest(".fr-modal__body") === null,
  () => {
    if (!props.closeOnBackdrop) return; 
    props.origin?.focus(); // DsfrModal le fait dans sa propre fermeture : on garde le retour du focus
    emit("close");
  },
);

// Le pied de la pop-up (boutons) est collant et recouvre le bas du contenu : sans espace réservé, un défilement
// automatique ou un focus peut laisser un champ caché derrière lui. DSFR prévoit pour cela la variable
// --modal-scroll-padding-bottom ; le projet n'importe pas le JavaScript de DSFR, donc on la renseigne ici.
const root = useTemplateRef<HTMLElement>("root");
let footerObserver: ResizeObserver | undefined;

watch(
  () => props.opened,
  async (isOpen) => {
    footerObserver?.disconnect();
    if (!isOpen) return;
    await nextTick(); // DsfrModal ne rend son contenu qu'une fois ouverte
    const body = root.value?.querySelector<HTMLElement>(".fr-modal__body");
      const footer = body?.querySelector<HTMLElement>(".fr-modal__footer");
    if (!body || !footer) return;
    footerObserver = new ResizeObserver(() =>
        body.style.setProperty("--modal-scroll-padding-bottom", `${footer.offsetHeight}px`),
    );
    footerObserver.observe(footer);
  },
  { immediate: true },
);
onBeforeUnmount(() => footerObserver?.disconnect());
</script>

<template>
  <!-- display: contents : aucune boîte ajoutée ; ce conteneur écoute seulement les événements qui remontent du <dialog>. -->
  <div ref="root" class="app-modal" @pointerdown.capture="backdrop.onPointerdown" @pointerup="backdrop.onPointerup" @click="backdrop.onClick">
    <DsfrModal v-bind="modalProps" disable-outside-interaction @close="emit('close')">
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
