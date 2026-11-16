<script setup lang="ts">
/**
 * Modal générique façon Muffin : overlay plein écran + carte centrée.
 * Utilisé pour afficher le changelog, les CGU, le signalement de bug, etc.
 *
 * La modal est redimensionnable : l'utilisateur peut tirer sur le bord
 * droit, le bord inférieur ou le coin bas-droit pour ajuster la taille.
 * La préférence est persistée en localStorage.
 */
import { onBeforeUnmount, ref, watch } from "vue";

defineProps<{
  title: string;
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

// --- Redimensionnement ---------------------------------------------------
// Taille persistée en localStorage (en px). On part des valeurs CSS par
// défaut (max-width: 48rem ≈ 768px, max-height: 80vh) la première fois.
const STORAGE_KEY = "millefeuille-modal-size";
const MIN_WIDTH = 320;
const MIN_HEIGHT = 240;

const modalWidth = ref(768);
const modalHeight = ref(600);

try {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    const parsed = JSON.parse(saved);
    if (parsed.width) modalWidth.value = parsed.width;
    if (parsed.height) modalHeight.value = parsed.height;
  }
} catch {
  // localStorage indisponible — on garde les valeurs par défaut.
}

function persistSize() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ width: modalWidth.value, height: modalHeight.value }));
  } catch {
    // Ignoré.
  }
}

type ResizeDir = "right" | "bottom" | "corner";

let resizing: { dir: ResizeDir; startX: number; startY: number; startW: number; startH: number } | null = null;

function startResize(dir: ResizeDir, event: PointerEvent) {
  event.preventDefault();
  event.stopPropagation();
  resizing = {
    dir,
    startX: event.clientX,
    startY: event.clientY,
    startW: modalWidth.value,
    startH: modalHeight.value,
  };
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", onPointerUp);
  document.body.style.userSelect = "none";
  document.body.style.cursor = dir === "corner" ? "nwse-resize" : dir === "right" ? "ew-resize" : "ns-resize";
}

function onPointerMove(event: PointerEvent) {
  if (!resizing) return;
  const dx = event.clientX - resizing.startX;
  const dy = event.clientY - resizing.startY;
  if (resizing.dir === "right" || resizing.dir === "corner") {
    modalWidth.value = Math.max(MIN_WIDTH, resizing.startW + dx);
  }
  if (resizing.dir === "bottom" || resizing.dir === "corner") {
    modalHeight.value = Math.max(MIN_HEIGHT, resizing.startH + dy);
  }
}

function onPointerUp() {
  if (resizing) {
    resizing = null;
    persistSize();
  }
  document.removeEventListener("pointermove", onPointerMove);
  document.removeEventListener("pointerup", onPointerUp);
  document.body.style.userSelect = "";
  document.body.style.cursor = "";
}

// Nettoyage au démontage.
onBeforeUnmount(() => {
  document.removeEventListener("pointermove", onPointerMove);
  document.removeEventListener("pointerup", onPointerUp);
});

// Réinitialise le curseur si la modal se ferme pendant un resize.
watch(() => undefined, () => {}, { immediate: true });
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="info-modal__overlay" @click.self="emit('close')">
      <div
        class="info-modal"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        :style="{ width: modalWidth + 'px', height: modalHeight + 'px', maxWidth: 'calc(100vw - 3rem)', maxHeight: 'calc(100vh - 3rem)' }"
      >
        <div class="info-modal__header">
          <h2 class="info-modal__title">{{ title }}</h2>
          <button
            type="button"
            class="info-modal__close"
            aria-label="Fermer"
            @click="emit('close')"
          >
            <VIcon name="ri-close-line" />
          </button>
        </div>
        <div class="info-modal__body">
          <slot />
        </div>

        <!-- Handles de redimensionnement -->
        <div class="info-modal__resize info-modal__resize--right" @pointerdown="startResize('right', $event)" />
        <div class="info-modal__resize info-modal__resize--bottom" @pointerdown="startResize('bottom', $event)" />
        <div class="info-modal__resize info-modal__resize--corner" @pointerdown="startResize('corner', $event)" />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.info-modal__overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: rgba(0, 0, 0, 0.4);
}

.info-modal {
  display: flex;
  flex-direction: column;
  background: var(--background-default-grey);
  border-radius: 0.5rem;
  box-shadow: var(--lifted-shadow);
  overflow: hidden;
  position: relative;
}

/* Handles de redimensionnement */
.info-modal__resize {
  position: absolute;
  z-index: 10;
}

.info-modal__resize--right {
  top: 0;
  right: 0;
  width: 6px;
  height: 100%;
  cursor: ew-resize;
}

.info-modal__resize--bottom {
  bottom: 0;
  left: 0;
  width: 100%;
  height: 6px;
  cursor: ns-resize;
}

.info-modal__resize--corner {
  bottom: 0;
  right: 0;
  width: 14px;
  height: 14px;
  cursor: nwse-resize;
  z-index: 11;
}

.info-modal__resize--corner::after {
  content: "";
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--text-mention-grey);
  border-bottom: 2px solid var(--text-mention-grey);
  border-bottom-right-radius: 2px;
  opacity: 0.5;
}

.info-modal__resize:hover::after,
.info-modal__resize--corner:hover::after {
  opacity: 1;
}

.info-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.info-modal__title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--text-title-grey);
}

.info-modal__close {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: none;
  border-radius: 0.375rem;
  background: transparent;
  color: var(--text-mention-grey);
  cursor: pointer;
  font-size: 1.25rem;
}

.info-modal__close:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

.info-modal__body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 1.5rem;
  overflow-y: auto;
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--text-default-grey);
}

/* Quand le slot contient un composant qui doit remplir la modal
 * (ex: HelperAgentModal), on retire le padding pour un rendu plein. */
.info-modal__body:has(> .helper-agent) {
  padding: 0;
  overflow: hidden;
}

.info-modal__body :deep(h2) {
  font-size: 1.1rem;
  font-weight: 700;
  margin: 1.5rem 0 0.5rem;
  color: var(--text-title-grey);
}

.info-modal__body :deep(h3) {
  font-size: 1rem;
  font-weight: 600;
  margin: 1rem 0 0.25rem;
  color: var(--text-title-grey);
}

.info-modal__body :deep(ul) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.info-modal__body :deep(li) {
  margin: 0.25rem 0;
}

.info-modal__body :deep(a) {
  color: var(--text-action-high-blue-france);
}

.info-modal__body :deep(code) {
  padding: 0.125rem 0.375rem;
  background: var(--background-alt-grey);
  border-radius: 0.25rem;
  font-size: 0.85em;
}

.info-modal__body :deep(pre) {
  padding: 0.75rem;
  background: var(--background-alt-grey);
  border-radius: 0.375rem;
  overflow-x: auto;
}
</style>
