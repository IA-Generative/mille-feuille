<script setup lang="ts">
import { ref, watch } from "vue";

import MarkdownText from "@/components/MarkdownText.vue";
import LlmAssistButton from "@/components/analyses/LlmAssistButton.vue";
import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { ASSIST_MIN_WORDS_HINT, hasEnoughWords } from "@/composables/useLlmAssist";
import type { PromptVersion } from "@/types/analyse";

const props = withDefaults(
  defineProps<{
    prompt: string;
    versions: PromptVersion[];
    suggestPrompt?: (draft: string, model: string | null) => Promise<string>;
    suggestLabel?: string;
  }>(),
  { suggestLabel: "Aide à la rédaction du prompt" },
);

const emit = defineEmits<{ save: [string]; restore: [string] }>();

const draft = ref(props.prompt);
const isDirty = ref(false);
const isSuggesting = ref(false);
// Aperçu rendu par défaut ; l'édition s'ouvre d'emblée tant qu'aucun prompt n'est défini.
const mode = ref<"preview" | "edit">(props.prompt.trim() ? "preview" : "edit");

watch(
  () => props.prompt,
  (prompt) => {
    draft.value = prompt;
    isDirty.value = false;
  },
);

watch(draft, (value) => {
  isDirty.value = value !== props.prompt;
});

async function applySuggestion(model: string | null) {
  if (!props.suggestPrompt) return;
  isSuggesting.value = true;
  try {
    draft.value = await props.suggestPrompt(draft.value, model);
    mode.value = "preview";
  } catch (error) {
    alert(error instanceof Error ? error.message : "Échec de l'aide LLM.");
  } finally {
    isSuggesting.value = false;
  }
}

function save() {
  emit("save", draft.value);
  mode.value = "preview";
}

function formatVersionContent(content: string) {
  return content;
}
</script>

<template>
  <div class="prompt-editor">
    <div class="prompt-editor__header">
      <h4 class="fr-h6 prompt-editor__title">Prompt</h4>
      <DsfrButtonGroup
        inline-layout-when="always"
        size="sm"
        :buttons="[
          { label: 'Aperçu', secondary: mode !== 'preview', onClick: () => (mode = 'preview') },
          { label: 'Modifier', secondary: mode !== 'edit', onClick: () => (mode = 'edit') },
        ]"
      />
    </div>
    <p class="fr-hint-text prompt-editor__hint">Version actuelle. {{ versions.length }} version(s) précédente(s).</p>

    <DsfrInput
      v-if="mode === 'edit'"
      v-model="draft"
      label="Prompt (Markdown)"
      label-visible
      is-textarea
      rows="16"
      class="prompt-editor__input"
    />
    <div v-else class="prompt-editor__preview">
      <MarkdownText v-if="draft.trim()" :content="draft" />
      <p v-else class="fr-text--sm prompt-editor__empty">Aucun prompt défini. Cliquez sur « Modifier » pour en rédiger un.</p>
    </div>

    <div class="prompt-editor__actions">
      <LlmAssistButton
        v-if="suggestPrompt"
        :label="suggestLabel"
        :loading="isSuggesting"
        :disabled="!hasEnoughWords(draft)"
        :disabled-hint="ASSIST_MIN_WORDS_HINT"
        @click="applySuggestion"
      />
      <DsfrButton label="Enregistrer" :disabled="!isDirty" size="sm" @click="save" />
    </div>

    <VersionHistory markdown :versions="versions" :format-content="formatVersionContent" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.prompt-editor {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.prompt-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.prompt-editor__title,
.prompt-editor__hint {
  margin: 0;
}

.prompt-editor__input :deep(textarea) {
  font-family: monospace;
  min-height: 20rem;
  resize: vertical;
}

.prompt-editor__preview {
  max-height: 32rem;
  overflow-y: auto;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.prompt-editor__empty {
  margin: 0;
  color: var(--text-mention-grey);
}

.prompt-editor__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
