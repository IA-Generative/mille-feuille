<script setup lang="ts">
import { computed, ref } from "vue";

import type { ChatToolCall, QuestionAnswer, ToolQuestion } from "@/types/conversation";

// Une question à choix de l'assistant : un onglet par question (au plus 4), des options à choix unique ou multiple, et
// toujours un champ « Autre » en texte libre. Une seule validation envoie toutes les réponses ; une question unique à
// choix unique part dès le clic. On répond tant qu'aucun autre message n'a été envoyé.
const props = defineProps<{ call: ChatToolCall; answerable: boolean; busy?: boolean }>();
const emit = defineEmits<{ answer: [answers: QuestionAnswer[]] }>();

const questions = computed<ToolQuestion[]>(() =>
  ((props.call.args.questions as any[]) ?? []).map((raw) => ({
    question: raw.question,
    header: raw.header || raw.question,
    multiSelect: raw.multi_select === true,
    options: raw.options ?? [],
  })),
);

const isOpen = computed(() => props.answerable && props.call.status === "pending");
const selectedTab = ref(0);
const picked = ref<string[][]>([]);
const others = ref<string[]>([]);

const pickedAt = (index: number) => picked.value[index] ?? [];
const otherAt = (index: number) => others.value[index]?.trim() ?? "";
const isAnswered = (index: number) => pickedAt(index).length > 0 || otherAt(index) !== "";
const allAnswered = computed(() => questions.value.every((_, index) => isAnswered(index)));
const direct = computed(() => questions.value.length === 1 && !questions.value[0].multiSelect);

const submit = () =>
  emit(
    "answer",
    questions.value.map((_, index) => ({
      selected: pickedAt(index),
      ...(otherAt(index) ? { other: otherAt(index) } : {}),
    })),
  );

function pick(index: number, label: string) {
  const question = questions.value[index];
  const current = pickedAt(index);
  picked.value[index] = question.multiSelect
    ? current.includes(label)
      ? current.filter((kept) => kept !== label)
      : [...current, label]
    : [label];
  // Un choix unique remplace le texte libre, et inversement : une réponse, pas deux.
  if (!question.multiSelect) others.value[index] = "";
  if (direct.value) return submit();
  if (!question.multiSelect && index < questions.value.length - 1) selectedTab.value = index + 1;
}

function writeOther(index: number, text: string) {
  others.value[index] = text;
  if (!questions.value[index].multiSelect && text.trim()) picked.value[index] = [];
}

function sendOther(index: number) {
  if (direct.value && otherAt(index)) submit();
  else if (otherAt(index) && index < questions.value.length - 1) selectedTab.value = index + 1;
}
</script>

<template>
  <section v-if="questions.length > 0" class="tool-question" aria-label="Question de l'assistant">
    <div v-if="questions.length > 1" class="tool-question__tabs" role="tablist">
      <button
        v-for="(question, index) in questions"
        :key="index"
        type="button"
        role="tab"
        class="tool-question__tab"
        :class="{ 'tool-question__tab--selected': index === selectedTab }"
        :aria-selected="index === selectedTab"
        @click="selectedTab = index"
      >
        {{ question.header }}
        <span v-if="isOpen && isAnswered(index)" class="tool-question__mark">✓</span>
      </button>
    </div>

    <template v-for="(question, index) in questions" :key="`q-${index}`">
      <fieldset v-if="index === selectedTab" class="tool-question__body" :disabled="!isOpen || busy">
        <legend class="tool-question__title">{{ question.question }}</legend>
        <p v-if="question.multiSelect" class="tool-question__hint">Plusieurs réponses possibles.</p>
        <label
          v-for="option in question.options"
          :key="option.label"
          class="tool-question__option"
          :class="{ 'tool-question__option--picked': pickedAt(index).includes(option.label) }"
        >
          <input
            :type="question.multiSelect ? 'checkbox' : 'radio'"
            :name="`question-${call.id}-${index}`"
            :checked="pickedAt(index).includes(option.label)"
            @change="pick(index, option.label)"
          />
          <span>
            <span class="tool-question__label">{{ option.label }}</span>
            <span v-if="option.description" class="tool-question__description">{{ option.description }}</span>
          </span>
        </label>
        <input
          type="text"
          maxlength="500"
          class="tool-question__other"
          placeholder="Autre…"
          aria-label="Autre réponse"
          :value="others[index] ?? ''"
          @input="writeOther(index, ($event.target as HTMLInputElement).value)"
          @keydown.enter.prevent="sendOther(index)"
        />
      </fieldset>
    </template>

    <footer v-if="isOpen && !direct" class="tool-question__footer">
      <DsfrButton label="Valider" size="sm" :disabled="!allAnswered || busy" @click="submit" />
    </footer>
    <p v-else-if="!isOpen" class="tool-question__status">
      {{ call.status === "executed" ? "Répondu" : "Sans réponse" }}
    </p>
  </section>
</template>

<style scoped>
.tool-question {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: min(100%, 36rem);
  margin-top: 0.5rem;
  padding: 1rem 1.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.tool-question__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.tool-question__tab {
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

.tool-question__tab--selected {
  background: #4b3fd9;
  color: #fff;
}

.tool-question__tab:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.tool-question__body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}

.tool-question__title {
  padding: 0;
  font-weight: 500;
}

.tool-question__hint,
.tool-question__status {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.tool-question__option {
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  cursor: pointer;
}

.tool-question__option:hover {
  background: var(--background-alt-grey);
}

.tool-question__option--picked {
  border-color: #4b3fd9;
  background: #4b3fd90d;
}

.tool-question__option:focus-within {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.tool-question__label {
  display: block;
  font-size: 0.875rem;
}

.tool-question__description {
  display: block;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.tool-question__other {
  padding: 0.5rem 0.875rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
}

.tool-question__other:focus-visible {
  outline: 2px solid #6a5cff;
  outline-offset: 2px;
}

.tool-question__footer {
  display: flex;
  justify-content: flex-end;
}
</style>
