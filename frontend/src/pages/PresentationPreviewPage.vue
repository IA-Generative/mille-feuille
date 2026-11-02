<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import ChatWindow, { type ChatWindowMessage } from "@/components/ChatWindow.vue";
import DossierPresentation from "@/components/presentation/DossierPresentation.vue";
import { useMockDossierPresentation, type MockScenario } from "@/composables/mockDossierPresentation";
import type { SuggestedQuestion } from "@/types/dossierPresentation";

// Aperçu de la présentation du dossier sur données simulées (développement seulement) : on y valide le rendu et les
// états avant que l'API existe. Le choix d'une question suggérée ajoute l'échange à la conversation, comme le fera la
// vraie page.
const scenario = ref<MockScenario>("ready");
const SCENARIOS: { id: MockScenario; label: string }[] = [
  { id: "ready", label: "Prête" },
  { id: "pending", label: "En cours" },
  { id: "failed", label: "Échec" },
  { id: "no-suggestions", label: "Sans suggestion" },
  { id: "no-summary", label: "Sans résumé" },
  { id: "summary-failed", label: "Résumé en échec" },
];

const { presentation, load } = useMockDossierPresentation();
const messages = ref<ChatWindowMessage[]>([]);
const asked = ref<string[]>([]);

async function reload() {
  await load(scenario.value);
  messages.value = [];
  asked.value = [];
}

function onAsk(question: SuggestedQuestion) {
  asked.value.push(question.id);
  messages.value.push(
    { id: `u-${question.id}`, role: "user", content: question.question },
    { id: `a-${question.id}`, role: "assistant", content: question.answer, sources: question.sources },
  );
}

onMounted(reload);
watch(scenario, reload);
</script>

<template>
  <div class="preview">
    <nav class="preview__scenarios" aria-label="Scénario simulé">
      <button
        v-for="item in SCENARIOS"
        :key="item.id"
        type="button"
        class="preview__scenario"
        :aria-pressed="scenario === item.id"
        @click="scenario = item.id"
      >
        {{ item.label }}
      </button>
    </nav>

    <ChatWindow
      :messages="messages"
      page-composer
      placeholder="Posez votre question sur ce dossier…"
      @submit="(text: string) => messages.push({ id: `u-${messages.length}`, role: 'user', content: text })"
    >
      <template v-if="presentation" #presentation>
        <DossierPresentation
          :presentation="{
            ...presentation,
            suggestions: presentation.suggestions.filter((q) => !asked.includes(q.id)),
          }"
          regenerable
          @ask="onAsk"
        />
      </template>
    </ChatWindow>
  </div>
</template>

<style scoped>
.preview__scenarios {
  display: flex;
  justify-content: center;
  gap: 0.5rem;
  padding: 1rem 0 0;
}

.preview__scenario {
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: transparent;
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}

.preview__scenario[aria-pressed="true"] {
  background: var(--background-contrast-grey);
  font-weight: 600;
}
</style>
