<script setup lang="ts">
/**
 * Composant de chat réutilisable, extrait de DossierDetailPage.vue.
 *
 * Affiche une liste de messages génériques, les événements de streaming
 * (tool_call, tool_result, thinking, done, error) pendant l'exécution du
 * graphe LangGraph, et un composer (textarea auto-agrandissable + bouton
 * envoyer). Les actions spécifiques au contexte (feedback thumbs up/down,
 * attachement de fichiers, sélection de modèle) sont déléguées au parent
 * via des slots et des events.
 *
 * Props :
 * - `messages` : liste de messages génériques (role, content, sources).
 * - `streamEvents` : événements de streaming en cours (affichés sous forme
 *   de "pensée" de l'assistant).
 * - `isRunning` : vrai pendant l'exécution (désactive le composer).
 * - `introTitle` / `introText` : texte affiché quand la liste est vide.
 * - `placeholder` : placeholder du textarea.
 * - `showFileAttach` : affiche le bouton d'attachement de fichiers (dossier).
 *
 * Slots :
 * - `message-extra` : contenu sous la bulle d'un message de l'assistant (ex : cartes de proposition).
 * - `message-actions` : actions par message (ex: feedback), reçoit
 *   `{ message }` en slot props.
 * - `source` : rendu personnalisé d'une source, reçoit `{ source }`.
 * - `composer-actions` : boutons ronds dans la zone d'envoi, après le trombone (ex: menu des outils).
 * - `composer-extra` : contenu supplémentaire avant le composer (ex: chips
 *   de fichiers en attente).
 *
 * Events :
 * - `submit` : émis avec le texte saisi quand l'utilisateur envoie.
 * - `attach-files` : émis avec les fichiers sélectionnés (si showFileAttach).
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import MarkdownText from "@/components/MarkdownText.vue";
import type { StreamEvent } from "@/composables/useChatStream";
import type { ChatToolCall } from "@/types/conversation";
import type { ExternalSource } from "@/types/knowledge";

// Ajout de l'util et du component pour le tool_call / tool_result
import { computed } from "vue";
import ToolSteps from "@/components/ToolSteps.vue";
import { parseAssistantSuggestion } from "@/utils/assistantSuggestion";
import { groupToolEvents } from "@/utils/groupToolEvents";


export interface ChatWindowMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: ChatWindowSource[];
  /** Feedback optionnel (thumbs up/down), utilisé par le chat de dossier. */
  feedback?: { value: "up" | "down" } | null;
  /** Outils demandés par l'assistant dans ce message (chat de dossier) ; la page les montre sous la bulle. */
  toolCalls?: ChatToolCall[];
  /** Les sources d'une base de connaissances externe citées par ce message (chat de dossier). */
  externalSources?: ExternalSource[];
}

export interface ChatWindowSource {
  id: string;
  excerpt?: string | null;
  pages?: { id: string; pageNumber: number }[];
  dossierDocumentId?: string | null;
  boundingBoxes?: { id: string; pageId: string; xMin: number; yMin: number; xMax: number; yMax: number }[];
}

const props = withDefaults(
  defineProps<{
    messages: ChatWindowMessage[];
    streamEvents?: StreamEvent[];
    isRunning?: boolean;
    introTitle?: string;
    introText?: string;
    placeholder?: string;
    showFileAttach?: boolean;
    /**
     * Chat intégré à une page qui défile (page d'un dossier) : la zone d'envoi reste collée au bas de l'écran sur
     * toute la hauteur de la page, pas seulement dans la section du chat (qui sort de l'écran quand on remonte).
     */
    pageComposer?: boolean;
    /** Des messages plus anciens existent côté serveur (pagination par curseur). */
    hasMore?: boolean;
    /** Une page de messages plus anciens est en cours de chargement. */
    loadingMore?: boolean;
    /** Texte à placer dans la zone de saisie (ex : question reprise d'un autre chat). */
    prefill?: string;
  }>(),
  {
    streamEvents: () => [],
    isRunning: false,
    introTitle: "Démarrez une conversation",
    introText: "",
    placeholder: "Écrivez votre message...",
    showFileAttach: false,
    pageComposer: false,
    hasMore: false,
    loadingMore: false,
    prefill: "",
  },
);

const toolSteps = computed(() => groupToolEvents(props.streamEvents));

const emit = defineEmits<{
  submit: [content: string];
  "attach-files": [files: File[]];
  /** Le haut de la discussion est atteint : charger les messages plus anciens. */
  "load-more": [];
}>();

const draft = ref(props.prefill);
watch(
  () => props.prefill,
  (value) => {
    if (value) {
      draft.value = value;
      nextTick(resizeTextarea);
    }
  },
);
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const messagesEndRef = ref<HTMLElement | null>(null);

const topSentinelRef = ref<HTMLElement | null>(null);

// Le bas de la discussion est-il visible ? Sinon, un bouton ramène au dernier message.
const atBottom = ref(true);
let bottomObserver: IntersectionObserver | undefined;

watch(
  messagesEndRef,
  (end) => {
    bottomObserver?.disconnect();
    bottomObserver = undefined;
    if (!end || typeof IntersectionObserver === "undefined") return;
    bottomObserver = new IntersectionObserver((entries) => {
      atBottom.value = entries.some((entry) => entry.isIntersecting);
    });
    bottomObserver.observe(end);
  },
  { flush: "post" },
);

function scrollToLastMessage() {
  messagesEndRef.value?.scrollIntoView({ behavior: "smooth", block: "end" });
}

// Conteneur qui défile réellement (la zone de messages ou, selon la mise en
// page, un ancêtre / la page) : nécessaire pour garder la position de lecture
// quand des messages plus anciens sont insérés au-dessus.
function getScrollParent(el: HTMLElement | null): HTMLElement {
  let node = el?.parentElement ?? null;
  while (node) {
    const overflowY = getComputedStyle(node).overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return (document.scrollingElement as HTMLElement) ?? document.documentElement;
}

let previousLastId: string | undefined;
let heightBeforePrepend: { scroller: HTMLElement; scrollHeight: number; scrollTop: number } | null = null;

watch(
  () => props.messages,
  (messages) => {
    const lastId = messages[messages.length - 1]?.id;
    const appended = lastId !== previousLastId;
    previousLastId = lastId;
    nextTick(() => {
      if (heightBeforePrepend) {
        // Messages plus anciens insérés en haut : on conserve la position.
        const { scroller, scrollHeight, scrollTop } = heightBeforePrepend;
        heightBeforePrepend = null;
        scroller.scrollTop = scrollTop + (scroller.scrollHeight - scrollHeight);
      } else if (appended) {
        messagesEndRef.value?.scrollIntoView({ behavior: "smooth" });
      }
    });
  },
  { deep: true },
);

// Défilement infini vers le haut : quand le repère en tête de liste devient
// visible, on demande la page de messages précédente. L'observateur est
// recréé à chaque fin de chargement : si le repère est encore visible (peu
// de contenu), la page suivante se charge sans attendre un nouveau scroll.
let observer: IntersectionObserver | undefined;

function requestOlderMessages() {
  if (!props.hasMore || props.loadingMore) return;
  const scroller = getScrollParent(topSentinelRef.value);
  heightBeforePrepend = { scroller, scrollHeight: scroller.scrollHeight, scrollTop: scroller.scrollTop };
  emit("load-more");
}

watch(
  [topSentinelRef, () => props.hasMore, () => props.loadingMore],
  ([sentinel, hasMore, loadingMore]) => {
    observer?.disconnect();
    observer = undefined;
    if (!sentinel || !hasMore || loadingMore || typeof IntersectionObserver === "undefined") return;
    observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) requestOlderMessages();
    });
    observer.observe(sentinel);
  },
  { flush: "post" },
);

onBeforeUnmount(() => {
  observer?.disconnect();
  bottomObserver?.disconnect();
});

watch(
  () => props.streamEvents,
  () => {
    nextTick(() => messagesEndRef.value?.scrollIntoView({ behavior: "smooth" }));
  },
  { deep: true },
);

function resizeTextarea() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
}

function openFilePicker() {
  fileInputRef.value?.click();
}

function onFilesSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  if (target.files) {
    emit("attach-files", Array.from(target.files));
  }
  target.value = "";
}

function submit() {
  const content = draft.value.trim();
  if (!content || props.isRunning) return;
  emit("submit", content);
  draft.value = "";
  nextTick(resizeTextarea);
}

// Un texte pré-rempli à l'ouverture doit aussi redimensionner la zone de saisie.
onMounted(() => {
  if (draft.value) nextTick(resizeTextarea);
});

defineExpose({ resizeTextarea });
</script>

<template>
  <section class="chat-window" :class="{ 'chat-window--page': pageComposer }">
    <header v-if="$slots.header" class="chat-window__header">
      <div class="chat-window__inner">
        <slot name="header" />
      </div>
    </header>

    <div v-if="messages.length === 0" class="chat-window__intro">
      <h2>{{ introTitle }}</h2>
      <p v-if="introText" class="fr-text--sm">{{ introText }}</p>
    </div>

    <div v-else class="chat-window__messages">
      <div class="chat-window__inner">
        <div v-if="hasMore" ref="topSentinelRef" class="chat-window__sentinel" aria-live="polite">
          <span v-if="loadingMore">Chargement des messages précédents…</span>
        </div>
        <div
          v-for="message in messages"
          :key="message.id"
          class="chat-message"
          :class="{ 'chat-message--assistant': message.role === 'assistant' }"
        >
          <div class="chat-message__bubble">
            <MarkdownText :content="parseAssistantSuggestion(message.content).text" class="chat-message__text" />
            <!-- Sources citées par l'assistant (repliées par défaut) -->
            <details v-if="message.sources && message.sources.length > 0" class="chat-message__sources">
              <summary class="chat-message__sources-title">
                Sources ({{ message.sources.length }})
              </summary>
              <ul>
                <li v-for="source in message.sources" :key="source.id" class="chat-message__source">
                  <slot name="source" :source="source">
                    <span v-if="source.pages && source.pages.length > 0" class="chat-message__source-pages">
                      {{ source.pages.map((p) => `p. ${p.pageNumber}`).join(", ") }}
                    </span>
                    <span v-if="source.excerpt" class="chat-message__source-excerpt">« {{ source.excerpt }} »</span>
                  </slot>
                </li>
              </ul>
            </details>
          </div>
          <!-- Contenu supplémentaire sous la bulle (ex : propositions de modification de l'analyse). -->
          <div v-if="message.role === 'assistant' && $slots['message-extra']" class="chat-message__extra">
            <slot name="message-extra" :message="message" />
          </div>
          <div v-if="message.role === 'assistant'" class="chat-message__feedback">
            <slot name="message-actions" :message="message" />
          </div>
        </div>

        <!-- Streaming en cours : événements du graphe LangGraph -->
        <div v-if="isRunning" class="chat-message chat-message--assistant chat-message--streaming">
          <!-- <div class="chat-message__bubble">
            <div v-for="event in streamEvents" :key="event.kind + JSON.stringify(event.data)" class="chat-message__event">
              <VIcon
                :name="
                  event.kind === 'tool_call'
                    ? 'ri-tools-line'
                    : event.kind === 'tool_result'
                      ? 'ri-check-line'
                      : event.kind === 'error'
                        ? 'ri-error-warning-line'
                        : 'ri-loader-4-line'
                "
              />
              <span>{{ event.data?.label || event.data?.tool || event.kind }}</span>
            </div>
            <div v-if="streamEvents.length === 0" class="chat-message__event chat-message__event--pending">
              <VIcon name="ri-loader-4-line" class="spin" />
              <span>Réflexion en cours…</span>
            </div>
          </div> -->
          <div class="chat-message__bubble">
            <ToolSteps :steps="toolSteps" />
            <div v-if="toolSteps.length === 0" class="chat-message__event chat-message__event--pending">
              <VIcon name="ri-loader-4-line" class="spin" />
              <span>Réflexion en cours…</span>
            </div>
          </div>
        </div>

        <div ref="messagesEndRef" />
      </div>
    </div>

    <form class="chat-window__form" @submit.prevent="submit">
      <button
        v-if="messages.length > 0 && !atBottom"
        type="button"
        class="chat-window__to-last"
        aria-label="Aller au dernier message"
        title="Aller au dernier message"
        @click="scrollToLastMessage"
      >
        <VIcon name="ri-arrow-down-line" />
        <span>Dernier message</span>
      </button>
      <div class="chat-window__inner">
        <slot name="composer-extra" />

        <div class="chat-window__composer">
          <input
            v-if="showFileAttach"
            ref="fileInputRef"
            type="file"
            multiple
            accept=".pdf,image/*"
            class="chat-window__file-input"
            aria-label="Choisir des documents à joindre"
            @change="onFilesSelected"
          />
          <button
            v-if="showFileAttach"
            type="button"
            class="chat-window__attach"
            aria-label="Joindre un document"
            title="Joindre un document"
            @click="openFilePicker"
          >
            <VIcon name="ri-attachment-2" />
          </button>
          <slot name="composer-actions" />
          <textarea
            ref="textareaRef"
            v-model="draft"
            class="chat-window__textarea"
            :placeholder="placeholder"
            aria-label="Message"
            rows="1"
            :disabled="isRunning"
            @input="resizeTextarea"
            @keydown.enter.exact.prevent="submit"
          />
          <button
            type="submit"
            class="chat-window__send"
            :disabled="isRunning || !draft.trim()"
            aria-label="Envoyer"
          >
            <VIcon name="ri-arrow-up-line" />
          </button>
        </div>
      </div>
    </form>
  </section>
</template>

<style scoped>
/* Style repris de Muffin (frontend/src/components/ChatWindow.vue et
   ChatMessage.vue) : colonne centrée, bulle grise arrondie à droite,
   composer en pilule arrondie avec textarea auto-agrandissante. */
.chat-window {
  flex: 1;
  min-width: 0;
  min-height: 16rem;
  display: flex;
  flex-direction: column;
}

/* Intégré à la page : la section disparaît de la mise en page, la zone d'envoi (sticky) a donc toute la page pour
   containing block et reste collée au bas de l'écran. */
.chat-window--page {
  display: contents;
}

.chat-window--page .chat-window__intro,
.chat-window--page .chat-window__messages {
  min-height: 12rem;
}

.chat-window__inner {
  max-width: 48rem;
  margin: 0 auto;
  padding: 0 0.5rem;
  width: 100%;
}

.chat-window__intro {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0.5rem;
  padding: 0 1.5rem;
  color: var(--text-mention-grey);
}

.chat-window__intro h2 {
  margin: 0;
  color: var(--text-default-grey);
}

.chat-window__intro p {
  max-width: 28rem;
}

.chat-window__sentinel {
  min-height: 1.5rem;
  text-align: center;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.chat-window__messages {
  flex: 1;
  overflow-y: auto;
  /* Position de lecture restaurée à la main à l'insertion des anciens messages. */
  overflow-anchor: none;
  padding-top: 1rem;
}

.chat-message {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  padding: 0.5rem 0;
}

.chat-message__bubble {
  max-width: min(75%, 40rem);
  min-width: 0;
  padding: 0.75rem 1.125rem;
  border-radius: 1.5rem;
  background: var(--background-contrast-grey);
  /* Mots/URL longs : on coupe plutôt que de déborder de la bulle. */
  overflow-wrap: anywhere;
}

/* Tableaux et blocs de code du markdown : défilent dans la bulle. */
.chat-message__bubble :deep(pre),
.chat-message__bubble :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
}

.chat-message__bubble :deep(img) {
  max-width: 100%;
  height: auto;
}

.chat-message__feedback {
  display: flex;
  gap: 0.25rem;
  margin-top: 0.25rem;
}

.chat-message__feedback-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-mention-grey);
  cursor: pointer;
  font-size: 0.9rem;
}

.chat-message__feedback-button:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

.chat-message__feedback-button--active {
  color: var(--text-active-blue-france);
  background: var(--background-action-low-blue-france);
}

/* Pas de white-space: pre-wrap : le markdown (breaks: true) gère déjà les
   retours à la ligne, et pre-wrap rendait le "\n" final de marked comme une
   ligne vide sous chaque bulle. */
.chat-message__text {
  margin: 0;
  line-height: 1.6;
}

/* Messages assistant : alignés à gauche, bulle neutre */
.chat-message--assistant {
  align-items: flex-start;
}

/* Façon ChatGPT : la réponse de l'assistant n'a pas de bulle, le texte
   occupe toute la largeur de la colonne ; seule la bulle de l'utilisateur
   (à droite) reste encadrée. */
.chat-message--assistant .chat-message__bubble {
  width: 100%;
  max-width: 100%;
  padding: 0.25rem 0;
  border-radius: 0;
  background: transparent;
}

/* Sources citées par l'assistant (bloc repliable) */
.chat-message__sources {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default-grey);
}

.chat-message__sources-title {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-mention-grey);
  cursor: pointer;
  list-style: none;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  user-select: none;
}

.chat-message__sources-title::-webkit-details-marker {
  display: none;
}

.chat-message__sources-title::before {
  content: "▸";
  font-size: 0.6rem;
  transition: transform 0.15s ease;
}

.chat-message__sources[open] .chat-message__sources-title::before {
  transform: rotate(90deg);
}

.chat-message__sources ul {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}

.chat-message__source {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding: 0;
  font-size: 0.8rem;
  color: var(--text-mention-grey);
}

.chat-message__source-pages {
  font-weight: 500;
  color: var(--text-default-grey);
}

.chat-message__source-excerpt {
  font-style: italic;
  color: var(--text-mention-grey);
}

/* Streaming en cours */
.chat-message--streaming .chat-message__bubble {
  opacity: 0.85;
}

.chat-message__event {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0;
  font-size: 0.8rem;
  color: var(--text-mention-grey);
}

.chat-message__event--pending {
  font-style: italic;
}

.chat-message__event .spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.chat-window__header {
  flex-shrink: 0;
  padding: 0 0 0.25rem;
}

/* Composer collé en bas de l'écran pendant que la discussion défile. */
.chat-window__to-last {
  position: absolute;
  bottom: calc(100% + 0.5rem);
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 999px;
  background: var(--background-default-grey);
  color: var(--text-action-high-blue-france);
  font: inherit;
  font-size: 0.875rem;
  box-shadow: 0 2px 8px rgb(0 0 0 / 12%);
  cursor: pointer;
}

.chat-window__to-last:hover {
  background: var(--background-alt-blue-france);
}

.chat-window__form {
  position: sticky;
  bottom: 0;
  z-index: 5;
  padding: 0.5rem 0 1rem;
  background: var(--background-default-grey);
  flex-shrink: 0;
}

.chat-window__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  list-style: none;
  margin: 0 0 0.5rem;
  padding: 0;
}

.chat-window__chip {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  border-radius: 1rem;
  border: 1px solid var(--border-action-high-blue-france);
  background: var(--background-alt-blue-france);
  color: var(--text-action-high-blue-france);
  font-size: 0.75rem;
}

.chat-window__chip button {
  display: flex;
  align-items: center;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0;
}

.chat-window__composer {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 0.5rem 0.5rem 1.25rem;
  border-radius: 1.75rem;
  border: none;
  background: var(--background-contrast-grey);
}

.chat-window__textarea {
  flex: 1;
  resize: none;
  border: none;
  background: transparent;
  color: var(--text-default-grey);
  font: inherit;
  line-height: 1.5;
  max-height: 200px;
  padding: 0.375rem 0;
}

.chat-window__textarea:focus {
  outline: none;
}

.chat-window__file-input {
  display: none;
}

.chat-window__attach,
.chat-window__send {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border: none;
  border-radius: 50%;
  cursor: pointer;
}

.chat-window__attach {
  background: transparent;
  color: var(--text-mention-grey);
}

.chat-window__attach:hover {
  background: var(--background-alt-grey-hover);
  color: var(--text-default-grey);
}

/* Bouton d'envoi rond et sombre, comme ChatGPT (jetons DSFR neutres). */
.chat-window__send {
  background: var(--text-title-grey);
  color: var(--background-default-grey);
}

.chat-window__send:disabled {
  background: var(--background-disabled-grey);
  color: var(--text-disabled-grey);
  cursor: not-allowed;
}

/* Tablettes / mobiles : bulles plus larges, composer plus compact. */
@media (max-width: 768px) {
  .chat-message__bubble {
    max-width: 92%;
    padding: 0.625rem 0.875rem;
    border-radius: 1rem;
  }

  .chat-message--assistant .chat-message__bubble {
    max-width: 100%;
    padding: 0.25rem 0;
    border-radius: 0;
  }

  .chat-window__composer {
    padding: 0.5rem 0.5rem 0.5rem 0.875rem;
    border-radius: 1.25rem;
  }

  .chat-window__textarea {
    /* 16px minimum : évite le zoom automatique d'iOS au focus. */
    font-size: 1rem;
  }
}

@media (max-width: 480px) {
  .chat-window__inner {
    padding: 0;
  }

  .chat-message__bubble {
    max-width: 100%;
  }

  .chat-window__intro {
    padding: 0 0.5rem;
  }
}
.chat-message__extra {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
  max-width: 100%;
}
</style>
