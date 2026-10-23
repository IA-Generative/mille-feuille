<script setup lang="ts">
import { ref } from "vue";

import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords } from "@/composables/useLlmAssist";
import { errorMessage } from "@/composables/useDocumentTemplates";

// Zone de texte avec un bouton d'aide à la rédaction (LLM). Le texte déjà saisi est transmis à l'aide pour être
// amélioré ; la suggestion remplace le contenu et reste modifiable, rien n'est enregistré sans action de l'utilisateur.
const props = defineProps<{
  modelValue: string;
  label: string;
  hint?: string;
  rows?: number;
  assistLabel: string;
  suggest: (draft: string, model: string | null) => Promise<string>;
}>();
const emit = defineEmits<{ "update:modelValue": [string] }>();

const loading = ref(false);
const error = ref("");

async function applySuggestion(model: string | null) {
  loading.value = true;
  error.value = "";
  try {
    emit("update:modelValue", (await props.suggest(props.modelValue, model)).trim());
  } catch (e) {
    error.value = errorMessage(e, "L'aide à la rédaction n'est pas disponible.");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="assisted-textarea">
    <div class="assisted-textarea__field">
      <DsfrInput
        :model-value="modelValue"
        :label="label"
        label-visible
        :hint="hint"
        is-textarea
        :rows="rows ?? 3"
        @update:model-value="emit('update:modelValue', String($event))"
      />
    </div>
    <LlmAssistButton
      compact
      :label="assistLabel"
      :loading="loading"
      :disabled="!hasEnoughWords(modelValue)"
      :disabled-hint="ASSIST_MIN_WORDS_HINT"
      class="assisted-textarea__assist"
      @click="applySuggestion"
    />
    <p v-if="error" class="fr-error-text assisted-textarea__error">{{ error }}</p>
  </div>
</template>

<style scoped>
.assisted-textarea {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.assisted-textarea__field {
  flex: 1 1 18rem;
  min-width: 0;
}

.assisted-textarea__assist {
  margin-top: 1.75rem;
}

.assisted-textarea__error {
  flex-basis: 100%;
  margin: 0;
}
</style>
