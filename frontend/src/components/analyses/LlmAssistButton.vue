<script setup lang="ts">
import { computed, onMounted } from "vue";

import ModelPicker from "@/components/ModelPicker.vue";
import { useModels } from "@/composables/useModels";

withDefaults(
  defineProps<{ label?: string; compact?: boolean; loading?: boolean; disabled?: boolean; disabledHint?: string }>(),
  {
    label: "Aide LLM",
    compact: false,
    loading: false,
    disabled: false,
    disabledHint: "",
  },
);
const emit = defineEmits<{ click: [model: string | null] }>();

// Préférence de modèle partagée par toute l'application (voir useModels.ts) :
// un bouton compact (aide inline sur un champ) réutilise la dernière valeur
// choisie ailleurs plutôt que d'afficher son propre sélecteur.
const { assistModel } = useModels();

function onClick() {
  emit("click", assistModel.value || null);
}
</script>

<template>
  <div class="llm-assist" :class="{ 'llm-assist--compact': compact }">
    <ModelPicker v-if="!compact" v-model="assistModel" :disabled="loading" />
    <button
      type="button"
      class="llm-assist-button"
      :class="{ 'llm-assist-button--compact': compact }"
      :title="disabled && disabledHint ? disabledHint : compact ? label : undefined"
      :disabled="loading || disabled"
      @click="onClick"
    >
      <VIcon
        :name="loading ? 'ri-loader-4-line' : 'ri-sparkling-2-fill'"
        class="llm-assist-button__icon"
        :class="{ 'llm-assist-button__icon--spin': loading }"
      />
      <span v-if="!compact">{{ loading ? "Génération..." : label }}</span>
      <span v-else class="fr-sr-only">{{ label }}</span>
    </button>
  </div>
</template>

<style scoped>
.llm-assist {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
}

.llm-assist-button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 1.5rem;
  background: linear-gradient(135deg, #5b4fd1 0%, #8b4fd6 50%, #d1477a 100%);
  color: #fff;
  font-weight: bold;
  font-size: 0.875rem;
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(91, 79, 209, 0.35);
  transition:
    transform 0.15s ease,
    box-shadow 0.15s ease,
    filter 0.15s ease;
}

.llm-assist-button--compact {
  padding: 0.4rem;
  border-radius: 50%;
}

.llm-assist-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(91, 79, 209, 0.45);
  filter: brightness(1.05);
}

.llm-assist-button:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(91, 79, 209, 0.35);
}

.llm-assist-button:focus-visible {
  outline: 2px solid #5b4fd1;
  outline-offset: 2px;
}

.llm-assist-button:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.llm-assist-button__icon {
  font-size: 1rem;
}

.llm-assist-button__icon--spin {
  animation: llm-assist-spin 0.8s linear infinite;
}

@keyframes llm-assist-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
