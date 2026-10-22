<script setup lang="ts">
import { computed, ref, watch } from "vue";

import ToolCallArguments from "@/components/tools/ToolCallArguments.vue";
import type { ChatToolCall, ToolCallStatus } from "@/types/conversation";

// La demande d'autorisation d'un message : une carte, un onglet par appel d'outil qui modifie des données (au plus 5),
// une seule validation. La décision relance le chat ; elle n'est possible que tant qu'aucun autre message n'a été envoyé.
const props = defineProps<{
  calls: ChatToolCall[];
  /** Le message est le dernier de la conversation et rien ne tourne : on peut encore décider. */
  answerable: boolean;
  busy?: boolean;
}>();
const emit = defineEmits<{ decide: [decisions: { id: string; allow: boolean; comment?: string }[]] }>();

const needsApproval = computed(() => props.calls.filter((call) => call.sideEffect));
const isOpen = computed(() => props.answerable && needsApproval.value.some((call) => call.status === "pending"));

const choices = ref<Record<string, { allow: boolean; comment?: string }>>({});
// Ce que la personne écrit pour refuser et dire quoi faire à la place, par appel.
const drafts = ref<Record<string, string>>({});
const selectedId = ref("");
watch(
  needsApproval,
  (calls) => {
    if (!calls.some((call) => call.id === selectedId.value)) selectedId.value = calls[0]?.id ?? "";
  },
  { immediate: true },
);

const selected = computed(() => needsApproval.value.find((call) => call.id === selectedId.value));
const allChosen = computed(() => needsApproval.value.every((call) => call.id in choices.value));

const labels: Record<ToolCallStatus, string> = {
  pending: "Sans réponse",
  approved: "Autorisé",
  executed: "Autorisé",
  refused: "Refusé",
  superseded: "Sans réponse",
};
const statusOf = (call: ChatToolCall) => (call.status === "pending" && !props.answerable ? "superseded" : call.status);

function mark(call: ChatToolCall) {
  if (isOpen.value) return call.id in choices.value ? (choices.value[call.id].allow ? "✓" : "✕") : "";
  return statusOf(call) === "refused" || statusOf(call) === "superseded" ? "✕" : "✓";
}

const submit = () =>
  emit(
    "decide",
    needsApproval.value.map((call) => ({ id: call.id, ...choices.value[call.id] })),
  );

// Une seule demande : le choix part tout de suite, comme une question à choix direct. Plusieurs : on choisit
// onglet par onglet, puis on valide le lot.
function choose(id: string, allow: boolean, comment?: string) {
  const text = comment?.trim();
  choices.value = { ...choices.value, [id]: allow ? { allow } : { allow, ...(text ? { comment: text } : {}) } };
  if (needsApproval.value.length === 1) return submit();
  const next = needsApproval.value.find((call) => !(call.id in choices.value));
  if (next) selectedId.value = next.id;
}

function chooseAll(allow: boolean) {
  choices.value = Object.fromEntries(needsApproval.value.map((call) => [call.id, { allow }]));
}
</script>

<template>
  <section
    v-if="needsApproval.length > 0"
    class="tool-call-card"
    :aria-label="isOpen ? 'Autoriser l\'utilisation d\'un outil' : 'Outils demandés par l\'assistant'"
  >
    <header class="tool-call-card__header">
      <span class="tool-call-card__icon"><VIcon name="ri-edit-2-line" /></span>
      <p class="tool-call-card__title">
        <template v-if="isOpen">
          {{ needsApproval.length > 1 ? "L'assistant souhaite utiliser des outils qui modifient des données" : "L'assistant souhaite utiliser un outil qui modifie des données" }}
        </template>
        <template v-else>Outil{{ needsApproval.length > 1 ? "s" : "" }} demandé{{ needsApproval.length > 1 ? "s" : "" }}</template>
      </p>
    </header>

    <div v-if="needsApproval.length > 1" class="tool-call-card__tabs" role="tablist">
      <button
        v-for="call in needsApproval"
        :id="`tool-tab-${call.id}`"
        :key="call.id"
        type="button"
        role="tab"
        class="tool-call-card__tab"
        :class="{ 'tool-call-card__tab--selected': call.id === selectedId }"
        :aria-selected="call.id === selectedId"
        @click="selectedId = call.id"
      >
        {{ call.toolName }}
        <span class="tool-call-card__mark">{{ mark(call) }}</span>
      </button>
    </div>

    <div v-if="selected" class="tool-call-card__body" role="tabpanel">
      <p class="tool-call-card__tool">
        <strong>{{ selected.toolName }}</strong>
        <span v-if="selected.serverName"> · serveur « {{ selected.serverName }} »</span>
      </p>
      <ToolCallArguments :args="selected.args" />
      <p v-if="!isOpen" class="tool-call-card__status">{{ labels[statusOf(selected)] }}</p>
      <template v-else>
        <div class="tool-call-card__choice">
          <DsfrButton label="Refuser" secondary size="sm" :disabled="busy" @click="choose(selected.id, false)" />
          <DsfrButton label="Autoriser" size="sm" :disabled="busy" @click="choose(selected.id, true)" />
        </div>
        <input
          v-model="drafts[selected.id]"
          type="text"
          maxlength="500"
          class="tool-call-card__comment"
          placeholder="Refuser et dire quoi faire à la place…"
          aria-label="Refuser et dire quoi faire à la place"
          :disabled="busy"
          @keydown.enter.prevent="drafts[selected.id]?.trim() && choose(selected.id, false, drafts[selected.id])"
        />
        <p v-if="selected.id in choices" class="tool-call-card__status">
          {{ choices[selected.id].allow ? "Sera autorisé" : "Sera refusé" }}
          <template v-if="choices[selected.id].comment"> : « {{ choices[selected.id].comment }} »</template>
        </p>
      </template>
    </div>

    <footer v-if="isOpen && needsApproval.length > 1" class="tool-call-card__footer">
      <button type="button" class="tool-call-card__link" @click="chooseAll(false)">Tout refuser</button>
      <button type="button" class="tool-call-card__link" @click="chooseAll(true)">Tout autoriser</button>
      <DsfrButton label="Valider" size="sm" :disabled="!allChosen || busy" @click="submit" />
    </footer>
  </section>
</template>

<style scoped>
.tool-call-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 0.5rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.tool-call-card__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.tool-call-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.75rem;
  background: #b340001a;
  color: #b34000;
  flex-shrink: 0;
}

.tool-call-card__title,
.tool-call-card__tool,
.tool-call-card__status {
  margin: 0;
}

.tool-call-card__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.tool-call-card__tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.75rem;
  border: 0;
  border-radius: 999px;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
  cursor: pointer;
}

.tool-call-card__tab--selected {
  background: #4b3fd9;
  color: #fff;
}

.tool-call-card__tab:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.tool-call-card__mark {
  min-width: 0.75rem;
  font-size: 0.75rem;
}

.tool-call-card__body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tool-call-card__status {
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-call-card__choice,
.tool-call-card__footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.5rem;
}

.tool-call-card__footer {
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default-grey);
}

.tool-call-card__comment {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
}

.tool-call-card__comment:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.tool-call-card__link {
  margin-right: auto;
  padding: 0;
  border: 0;
  background: none;
  font-size: 0.8125rem;
  color: var(--text-action-high-blue-france);
  cursor: pointer;
}

.tool-call-card__link + .tool-call-card__link {
  margin-right: 0;
}
</style>
