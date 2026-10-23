<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import AccessBadge from "@/components/access/AccessBadge.vue";
import WorkflowStatusPicker from "@/components/statuses/WorkflowStatusPicker.vue";
import AccessModal from "@/components/access/AccessModal.vue";
import ModelPicker from "@/components/ModelPicker.vue";
import ChatWindow, { type ChatWindowSource } from "@/components/ChatWindow.vue";
import SourceViewerModal from "@/components/SourceViewerModal.vue";
import DueDatePicker from "@/components/dossiers/DueDatePicker.vue";
import AddDocumentsModal from "@/components/dossiers/AddDocumentsModal.vue";
import DossierDocuments from "@/components/dossiers/DossierDocuments.vue";
import DossierResults from "@/components/dossiers/DossierResults.vue";
import RelaunchBanner from "@/components/dossiers/RelaunchBanner.vue";
import FeedbackReasonsModal from "@/components/dossiers/FeedbackReasonsModal.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useChatStream } from "@/composables/useChatStream";
import ChatProposals from "@/components/analysis/ChatProposals.vue";
import { parseAssistantSuggestion, parseMessageMarkers } from "@/utils/assistantSuggestion";
import { chatSourcesOf } from "@/utils/chatSources";
import { setDocumentSource, useDossierSources } from "@/composables/useDocumentSources";
import ChatToolsMenu from "@/components/tools/ChatToolsMenu.vue";
import SourceCarousel from "@/components/tools/SourceCarousel.vue";
import ToolCallCard from "@/components/tools/ToolCallCard.vue";
import ToolQuestionCard from "@/components/tools/ToolQuestionCard.vue";
import { useConversations } from "@/composables/useConversations";
import { useDossiers } from "@/composables/useDossiers";
import { useHelperAgent } from "@/composables/useHelperAgent";
import { useMyConversations } from "@/composables/useMyConversations";
import type { FeedbackReasonCode, QuestionAnswer } from "@/types/conversation";
import {
  DOSSIER_STATUS_LABELS,
  SUGGESTION_STATUS_LABELS,
  type DossierStatus,
  type SuggestionStatus,
} from "@/types/dossier";

const route = useRoute();
const dossierId = String(route.params.id);
const { openHelper } = useHelperAgent();
const {
  list: dossiers,
  fetchDossier,
  streamDossier,
  regenerateDossierSummary,
  suggestAnalyse,
  assignAnalyse,
  setWorkflowStatus,
  setDueAt,
  launch,
} = useDossiers();
const { getById: getAnalyseById, fetchAnalyse } = useAnalyses();
const {
  conversation,
  messages,
  hasMoreMessages,
  isLoadingMore,
  loadOlderMessages,
  ensureConversation,
  sendMessage,
  decideToolCalls,
  answerToolQuestion,
  refreshConversation,
  deleteConversation,
  setModel,
  setFeedback,
  removeFeedback,
} = useConversations(dossierId);
const { fetchList: refreshSidebarConversations } = useMyConversations();

// Pouce haut : bascule directement. Pouce bas : ouvre une modale pour
// recueillir la/les raison(s) avant d'envoyer (comme Muffin).
const feedbackReasonsModalOpened = ref(false);
const pendingDownMessageId = ref<string | null>(null);

// Streaming du chat : événements reçus pendant l'exécution du graphe
// LangGraph (tool_call, tool_result, done, error). Affichés en temps réel
// sous la forme d'une "pensée" de l'assistant.
const chatEvents = ref<{ kind: string; data: Record<string, unknown> }[]>([]);
const { isRunning: isChatRunning, start: startChatStream, stop: stopChatStream } = useChatStream({
  onEvent: (event) => chatEvents.value.push(event),
  onDone: async () => {
    // done : recharge la conversation pour récupérer le message assistant
    // final avec ses sources, puis ferme le streaming.
    await refreshConversation();
    await refreshSidebarConversations();
    chatEvents.value = [];
  },
});

const isDetailsModalOpened = ref(false);
const isAccessOpened = ref(false);

// Ajout de fichiers après coup, avec leur source. Jamais refusé : on prévient simplement qu'il faut relancer.
const isAddDocumentsOpened = ref(false);
// Fichiers joints depuis le chat : la modale d'ajout s'ouvre avec eux, pour choisir leur source avant l'envoi.
const attachedFiles = ref<File[]>([]);

function openAddDocuments(files: File[] = []) {
  attachedFiles.value = files;
  isAddDocumentsOpened.value = true;
}
const { sources: documentSources, load: loadDocumentSources } = useDossierSources(dossierId);
// Fichiers ajoutés à un dossier « à ranger » depuis les dernières suggestions : à regénérer.
const addedSinceSuggestions = ref(0);

async function onDocumentsAdded(count: number) {
  addedSinceSuggestions.value += count;
  await Promise.all([fetchDossier(dossierId), loadDocumentSources()]);
}

async function onChangeDocumentSource(documentId: string, sourceId: string | null) {
  await setDocumentSource(dossierId, documentId, sourceId);
  await fetchDossier(dossierId);
}

async function onSuggestAnalyse() {
  addedSinceSuggestions.value = 0;
  await suggestAnalyse(dossierId);
}

// Source citée par l'assistant, ouverte dans une modale (page + passage surligné).
const viewedSource = ref<ChatWindowSource | null>(null);
const isSourceOpened = ref(false);
function openSource(source: ChatWindowSource) {
  viewedSource.value = source;
  isSourceOpened.value = true;
}

function formatDateTime(iso?: string) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function thumbUp(messageId: string) {
  const current = messages.value.find((m) => m.id === messageId)?.feedback;
  if (current?.value === "up") removeFeedback(messageId);
  else setFeedback(messageId, "up");
}

function thumbDown(messageId: string) {
  const current = messages.value.find((m) => m.id === messageId)?.feedback;
  if (current?.value === "down") {
    removeFeedback(messageId);
    return;
  }
  pendingDownMessageId.value = messageId;
  feedbackReasonsModalOpened.value = true;
}

function submitDownFeedback(reasons: FeedbackReasonCode[], comment: string | null) {
  if (!pendingDownMessageId.value) return;
  setFeedback(pendingDownMessageId.value, "down", reasons, comment);
  pendingDownMessageId.value = null;
}

function onModelChange(value: string) {
  setModel(value || null);
}

// Autorisation d'un outil qui modifie des données : la décision relance le chat, dont on suit la nouvelle exécution.
const isDeciding = ref(false);
async function onToolCallsDecided(decisions: { id: string; allow: boolean; comment?: string }[]) {
  if (isChatRunning.value || isDeciding.value) return;
  isDeciding.value = true;
  try {
    const current = await ensureConversation();
    chatEvents.value = [];
    await decideToolCalls(decisions);
    startChatStream(`/api/dossiers/${dossierId}/conversations/${current.id}/stream`);
  } finally {
    isDeciding.value = false;
  }
}
// Réponse à une question à choix de l'assistant : même suite qu'une décision d'outil, le chat est relancé.
async function onQuestionAnswered(callId: string, answers: QuestionAnswer[]) {
  if (isChatRunning.value || isDeciding.value) return;
  isDeciding.value = true;
  try {
    const current = await ensureConversation();
    chatEvents.value = [];
    await answerToolQuestion(callId, answers);
    startChatStream(`/api/dossiers/${dossierId}/conversations/${current.id}/stream`);
  } finally {
    isDeciding.value = false;
  }
}
const isLastMessage = (messageId: string) => messages.value[messages.value.length - 1]?.id === messageId;

const dossier = computed(() => dossiers.value.find((d) => d.id === dossierId));
// Le nom d'un document du dossier, pour le titre d'une source citée.
const documentName = (documentId: string) => dossier.value?.documents.find((d) => d.id === documentId)?.name;
const analyse = computed(() =>
  dossier.value?.analyseId ? getAnalyseById(dossier.value.analyseId) : undefined,
);

// SSE : on s'abonne au flux du dossier pour suivre en temps réel l'état
// d'extraction de texte des documents (et plus tard l'exécution). Le serveur
// émet `done` quand il n'y a plus de travail actif, puis on ferme.
let closeStream: (() => void) | undefined;

onMounted(async () => {
  // ensureConversation() crée la conversation de cet utilisateur pour ce
  // dossier si elle n'existe pas encore : c'est ce qui la fait apparaître
  // dans la sidebar (voir App.vue, qui rafraîchit aussi sur la navigation).
  await ensureConversation();
  refreshSidebarConversations();
  // Le dossier n'est pas forcément dans la page actuellement chargée par
  // DossiersPage (pagination côté serveur) : on le charge directement.
  const loaded = await fetchDossier(dossierId);
  if (loaded.analyseId) await fetchAnalyse(loaded.analyseId);
  await loadDocumentSources();
  closeStream = streamDossier(dossierId, () => {});
});

onUnmounted(() => {
  closeStream?.();
  stopChatStream();
});
watch(
  () => dossier.value?.analyseId,
  (analyseId) => {
    if (analyseId) fetchAnalyse(analyseId);
  },
);

const statusBadgeType: Record<DossierStatus, "new" | "info" | "success" | "warning" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  arrêté: "warning",
  échec: "error",
};

const suggestionBadgeType: Record<SuggestionStatus, "new" | "info" | "success" | "warning" | "error"> = {
  en_attente: "new",
  en_cours: "info",
  terminé: "success",
  échec: "error",
};

const isUnassigned = computed(() => !dossier.value?.analyseId);

const statusError = ref("");
// Relance de l'analyse (échec, ou analyse mise à jour depuis le dernier lancement). Le flux du dossier s'était fermé
// à la fin de la dernière exécution : on le rouvre pour suivre la nouvelle.
const relaunchBusy = ref(false);
const relaunchError = ref<string | undefined>(undefined);
const canRelaunch = computed(
  () => !isUnassigned.value && !!dossier.value && ["terminé", "arrêté", "échec"].includes(dossier.value.status),
);

// Fichiers déposés après le dernier lancement : l'analyse ne les a pas vus.
const newDocumentsCount = computed(() => {
  const started = dossier.value?.startedAt;
  if (!started || isUnassigned.value) return 0;
  return dossier.value!.documents.filter((d) => d.createdAt && d.createdAt > started).length;
});
const isRunning = computed(() => dossier.value?.status === "en_cours");

async function onRelaunch() {
  relaunchBusy.value = true;
  relaunchError.value = undefined;
  try {
    await launch(dossierId);
    closeStream?.();
    closeStream = streamDossier(dossierId, () => {});
  } catch (e) {
    relaunchError.value = e instanceof Error ? e.message : "Impossible de relancer l'analyse";
  } finally {
    relaunchBusy.value = false;
  }
}

const dueBusy = ref(false);
async function onDueChange(dueAt: string | null) {
  statusError.value = "";
  dueBusy.value = true;
  try {
    await setDueAt(dossierId, dueAt);
  } catch (e) {
    statusError.value = e instanceof Error ? e.message : "Le changement d'échéance a échoué.";
  } finally {
    dueBusy.value = false;
  }
}
async function onWorkflowStatusChange(statusId: string) {
  statusError.value = "";
  try {
    await setWorkflowStatus(dossierId, statusId);
  } catch (e) {
    statusError.value = e instanceof Error ? e.message : "Le changement de statut a échoué.";
  }
}

// Fil d'échange pour alimenter l'analyse : les résultats eux-mêmes sont
// présentés directement dans DossierResults, pas ici, pour rester visibles
// sans avoir à remonter la conversation. Les messages sont chargés par pages
// (les plus anciens au défilement vers le haut, voir useConversations).

async function onChatSubmit(content: string) {
  if (!dossier.value) return;
  if (isChatRunning.value) return;

  const current = await ensureConversation();
  chatEvents.value = [];
  // Le streaming démarre APRÈS l'envoi : POST /messages purge les événements
  // du tour précédent. Ouvert avant, le flux rejouerait l'ancien `done`,
  // se fermerait aussitôt et rechargerait la conversation sans la réponse.
  // Rien n'est manqué : les événements sont en base et rejoués depuis le début.
  await sendMessage(content);
  startChatStream(`/api/dossiers/${dossierId}/conversations/${current.id}/stream`);
}

async function onDeleteConversation() {
  if (!confirm("Supprimer cette conversation ? Le dossier et ses documents ne seront pas affectés.")) return;
  // Ne supprime que la conversation : le dossier reste ouvert, on en
  // recrée aussitôt une nouvelle (vide) pour pouvoir continuer à échanger.
  await deleteConversation();
  await ensureConversation();
  refreshSidebarConversations();
}
</script>

<template>
  <div v-if="dossier" class="dossier-detail">
    <RouterLink to="/dossiers" class="fr-link fr-icon-arrow-left-line fr-link--icon-left dossier-detail__back">
      Retour aux dossiers
    </RouterLink>

    <div class="dossier-detail__header">
      <div>
        <div class="dossier-detail__title">
          <h1 class="fr-h2">{{ dossier.name }}</h1>
          <AccessBadge :visibility="dossier.visibility" />
          <button
            type="button"
            class="dossier-detail__icon-button"
            aria-label="Voir le détail du dossier"
            title="Voir le détail du dossier"
            @click="isDetailsModalOpened = true"
          >
            <VIcon name="ri-information-line" />
          </button>
        </div>
        <p class="fr-text--sm">
          <template v-if="isUnassigned">
            <DsfrBadge
              :label="SUGGESTION_STATUS_LABELS[dossier.suggestionStatus]"
              :type="suggestionBadgeType[dossier.suggestionStatus]"
              small
            />
            <span class="dossier-detail__a-ranger-label">Dossier à ranger — aucune analyse rattachée</span>
          </template>
          <template v-else>
            Analyse : <RouterLink :to="`/analyses/${dossier.analyseId}`">{{ analyse?.name ?? "introuvable" }}</RouterLink>
            · Version {{ dossier.analyseVersion }}
          </template>
        </p>
        <!-- Statut de dossier (#170) : propre à l'analyse ; absent d'un dossier « à ranger ». -->
        <WorkflowStatusPicker
          v-if="!isUnassigned && analyse"
          :statuses="analyse.statuses"
          :current="dossier.workflowStatus"
          :closed-at="dossier.closedAt"
          @change="onWorkflowStatusChange"
        />
        <!-- Échéance (#172) : niveau et couleur calculés par le serveur selon les seuils de l'analyse. -->
        <DueDatePicker
          v-if="!isUnassigned"
          :due-at="dossier.dueAt"
          :due="dossier.due"
          :busy="dueBusy"
          @change="onDueChange"
        />
        <p v-if="statusError" class="fr-error-text" role="alert">{{ statusError }}</p>
      </div>
      <div class="dossier-detail__header-actions">
        <ModelPicker
          :model-value="conversation?.model ?? ''"
          align="right"
          @update:model-value="onModelChange"
        />
        <button
          type="button"
          class="dossier-detail__icon-button"
          aria-label="Ajouter des documents au dossier"
          title="Ajouter des documents au dossier"
          @click="openAddDocuments()"
        >
          <VIcon name="ri-attachment-2" />
        </button>
        <button
          type="button"
          class="dossier-detail__icon-button"
          aria-label="Accès au dossier"
          title="Accès : qui peut voir ce dossier"
          @click="isAccessOpened = true"
        >
          <VIcon name="ri-lock-line" />
        </button>
        <RouterLink
          :to="`/dossiers/${dossierId}/historique`"
          class="dossier-detail__icon-button"
          aria-label="Voir l'historique du dossier"
          title="Historique : qui a fait quoi sur ce dossier, et quand"
        >
          <VIcon name="ri-history-line" />
        </RouterLink>
        <RouterLink
          :to="`/dossiers/${dossierId}/analyse`"
          class="dossier-detail__icon-button"
          aria-label="Voir l'analyse du dossier"
          title="Analyse du dossier : éléments, historique et propositions"
        >
          <VIcon name="ri-file-list-3-line" />
        </RouterLink>
        <RouterLink
          :to="`/dossiers/${dossierId}/documents`"
          class="dossier-detail__icon-button"
          aria-label="Voir les documents du dossier"
          title="Documents de fin d'instruction : créer, relire, générer et télécharger"
        >
          <VIcon name="ri-file-word-2-line" />
        </RouterLink>
        <button
          type="button"
          class="dossier-detail__icon-button"
          aria-label="Ouvrir l'assistant de l'application"
          title="Assistant de l'application : créer ou lancer une analyse, piloter l'application"
          @click="openHelper({ dossierId: dossier.id, name: dossier.name })"
        >
          <VIcon name="ri-robot-2-line" />
        </button>
        <DsfrBadge :label="DOSSIER_STATUS_LABELS[dossier.status]" :type="statusBadgeType[dossier.status]" />
        <button
          type="button"
          class="dossier-detail__icon-button"
          aria-label="Supprimer cette conversation"
          title="Supprimer cette conversation"
          @click="onDeleteConversation"
        >
          <VIcon name="ri-delete-bin-line" />
        </button>
      </div>
    </div>

    <!-- Suggestions d'analyse pour les dossiers « à ranger » (issue #54) -->
    <div v-if="isUnassigned" class="dossier-detail__suggestions">
      <div class="dossier-detail__suggestions-header">
        <h2 class="fr-h3">Suggestions d'analyse</h2>
        <DsfrButton
          label="Générer les suggestions"
          icon="ri-lightbulb-flash-line"
          secondary
          :disabled="dossier.suggestionStatus === 'en_cours'"
          @click="onSuggestAnalyse"
        />
      </div>

      <DsfrAlert
        v-if="addedSinceSuggestions > 0 && dossier.suggestionStatus !== 'en_cours'"
        type="warning"
        :description="`${addedSinceSuggestions === 1 ? 'Un fichier a été ajouté' : `${addedSinceSuggestions} fichiers ont été ajoutés`} : les suggestions n'en tiennent pas compte, régénérez-les.`"
        small
        class="fr-mb-2w"
      />

      <DsfrAlert
        v-if="dossier.suggestionStatus === 'en_cours'"
        type="info"
        title="Génération en cours..."
        description="Le LLM analyse les résumés des documents pour identifier les analyses les plus pertinentes."
        small
      />

      <DsfrAlert
        v-else-if="dossier.suggestionStatus === 'en_attente'"
        type="info"
        title="Aucune suggestion générée"
        description="Cliquez sur « Générer les suggestions » pour que le LLM propose des analyses pertinentes à partir des résumés des documents."
        small
      />

      <DsfrAlert
        v-else-if="dossier.suggestionStatus === 'échec'"
        type="error"
        title="Échec de la génération"
        description="La génération des suggestions a échoué. Vous pouvez réessayer."
        small
      />

      <div v-if="dossier.suggestedAnalyses && dossier.suggestedAnalyses.length > 0" class="dossier-detail__suggestion-list">
        <div
          v-for="suggestion in dossier.suggestedAnalyses"
          :key="suggestion.analyseId"
          class="dossier-detail__suggestion-card"
        >
          <div class="dossier-detail__suggestion-info">
            <span class="dossier-detail__suggestion-name">{{ suggestion.name }}</span>
            <span class="dossier-detail__suggestion-score">Score : {{ Math.round(suggestion.score * 100) }}%</span>
          </div>
          <p class="fr-text--sm dossier-detail__suggestion-rationale">{{ suggestion.rationale }}</p>
          <DsfrButton
            label="Rattacher cette analyse"
            icon="ri-link"
            size="sm"
            @click="assignAnalyse(dossierId, suggestion.analyseId)"
          />
        </div>
      </div>
    </div>

    <RelaunchBanner
      v-if="!isUnassigned && (canRelaunch || newDocumentsCount > 0)"
      :new-documents="newDocumentsCount"
      :running="isRunning"
      :failed="dossier.status === 'échec'"
      :launched-version="dossier.analyseVersion"
      :current-version="analyse?.version"
      :busy="relaunchBusy"
      @relaunch="onRelaunch"
    />
    <DsfrAlert v-if="relaunchError" type="error" :title="relaunchError" small class="fr-mb-2w" />

    <DossierResults :dossier="dossier" :analyse="analyse" @regenerate-summary="regenerateDossierSummary(dossierId)" />

    <ChatWindow
      :messages="messages"
      :has-more="hasMoreMessages"
      :loading-more="isLoadingMore"
      @load-more="loadOlderMessages"
      :stream-events="chatEvents"
      :is-running="isChatRunning"
      page-composer
      show-file-attach
      intro-title="Alimenter l'analyse"
      intro-text="Posez une question ou ajoutez une note pour compléter ce dossier. Les résultats de l'analyse s'affichent ci-dessus."
      placeholder="Alimentez l'analyse avec un message..."
      @attach-files="openAddDocuments"
      @submit="onChatSubmit"
    >
      <template #message-sources="{ message }">
        <SourceCarousel
          :sources="chatSourcesOf(message, documentName)"
          :dossier-id="dossierId"
          :message-id="message.id"
          @open="(source) => source.dossier && openSource(source.dossier.source)"
        />
      </template>

      <template #composer-actions>
        <ChatToolsMenu :dossier-id="dossierId" :conversation-id="conversation?.id" />
      </template>

      <template #message-extra="{ message }">
        <ToolCallCard
          v-if="message.toolCalls?.length"
          :calls="message.toolCalls"
          :answerable="isLastMessage(message.id) && !isChatRunning"
          :busy="isDeciding"
          @decide="onToolCallsDecided"
        />
        <ToolQuestionCard
          v-for="call in message.toolCalls?.filter((c) => c.toolId === 'ask_user') ?? []"
          :key="call.id"
          :call="call"
          :answerable="isLastMessage(message.id) && !isChatRunning"
          :busy="isDeciding"
          @answer="(answers) => onQuestionAnswered(call.id, answers)"
        />
        <ChatProposals
          v-if="parseMessageMarkers(message.content).proposals"
          :dossier-id="dossierId"
          :analysis-id="parseMessageMarkers(message.content).proposals!.analysisId"
          :proposal-ids="parseMessageMarkers(message.content).proposals!.proposalIds"
        />
      </template>

      <template #message-actions="{ message }">
        <button
          v-if="parseAssistantSuggestion(message.content).question && dossier"
          type="button"
          class="dossier-detail__assistant-suggestion"
          @click="
            openHelper({
              dossierId: dossier.id,
              name: dossier.name,
              question: parseAssistantSuggestion(message.content).question ?? undefined,
            })
          "
        >
          <VIcon name="ri-robot-2-line" />
          <span>Ouvrir l'assistant</span>
        </button>
        <button
          type="button"
          class="chat-message__feedback-button"
          :class="{ 'chat-message__feedback-button--active': message.feedback?.value === 'up' }"
          aria-label="Bonne réponse"
          title="Bonne réponse"
          @click="thumbUp(message.id)"
        >
          <VIcon name="ri-thumb-up-line" />
        </button>
        <button
          type="button"
          class="chat-message__feedback-button"
          :class="{ 'chat-message__feedback-button--active': message.feedback?.value === 'down' }"
          aria-label="Mauvaise réponse"
          title="Mauvaise réponse"
          @click="thumbDown(message.id)"
        >
          <VIcon name="ri-thumb-down-line" />
        </button>
      </template>
    </ChatWindow>

    <AddDocumentsModal
      v-model:opened="isAddDocumentsOpened"
      :dossier-id="dossierId"
      :initial-files="attachedFiles"
      @added="onDocumentsAdded"
    />

    <AccessModal v-if="isAccessOpened" :dossier-id="dossier.id" :dossier-name="dossier.name" @close="isAccessOpened = false" />

    <SourceViewerModal
      :opened="isSourceOpened"
      :dossier-id="dossierId"
      :source="viewedSource"
      @close="isSourceOpened = false"
    />

    <DsfrModal
      :opened="isDetailsModalOpened"
      @close="isDetailsModalOpened = false"
      title="Détail du dossier"
      icon="ri-folder-info-line"
      size="lg"
    >
      <dl class="dossier-details-modal__info">
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Nom</dt>
          <dd>{{ dossier.name }}</dd>
        </div>
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Statut</dt>
          <dd>
            <DsfrBadge :label="DOSSIER_STATUS_LABELS[dossier.status]" :type="statusBadgeType[dossier.status]" small />
          </dd>
        </div>
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Créé le</dt>
          <dd>{{ formatDateTime(dossier.createdAt) }}</dd>
        </div>
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Lancé le</dt>
          <dd>{{ formatDateTime(dossier.startedAt) }}</dd>
        </div>
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Terminé le</dt>
          <dd>{{ formatDateTime(dossier.endedAt) }}</dd>
        </div>
        <div class="dossier-details-modal__row">
          <dt class="fr-text--sm">Analyse</dt>
          <dd v-if="dossier.analyseId">
            <RouterLink :to="`/analyses/${dossier.analyseId}`" class="fr-link" @click="isDetailsModalOpened = false">
              {{ analyse?.name ?? "introuvable" }}
            </RouterLink>
            · Version {{ dossier.analyseVersion }}
          </dd>
          <dd v-else>
            <em>Dossier à ranger — aucune analyse rattachée</em>
          </dd>
        </div>
      </dl>

      <div v-if="dossier.documents.length === 0">
        <p class="fr-text--sm dossier-details-modal__no-files">Aucun fichier pour l'instant.</p>
        <DsfrButton label="Ajouter des documents" icon="ri-add-line" size="sm" secondary @click="openAddDocuments()" />
      </div>
      <DossierDocuments
        v-else
        :documents="dossier.documents"
        :sources="documentSources"
        can-add
        @add="openAddDocuments()"
        @change-source="onChangeDocumentSource"
      />
    </DsfrModal>

    <FeedbackReasonsModal v-model:opened="feedbackReasonsModalOpened" @submit="submitDownFeedback" />
  </div>
  <div v-else>
    <p>Dossier introuvable.</p>
    <RouterLink to="/dossiers" class="fr-link">Retour aux dossiers</RouterLink>
  </div>
</template>

<style scoped>
.dossier-detail {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 8rem);
}

.dossier-detail__back {
  display: inline-flex;
  margin-bottom: 1.5rem;
  flex-shrink: 0;
}

.dossier-detail__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.5rem;
  flex-shrink: 0;
}

.dossier-detail__title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.dossier-detail__title .fr-h2 {
  margin-bottom: 0;
}

.dossier-detail__header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* Source citée dans une réponse : pastille compacte, ouvre la page dans une modale. */


.dossier-detail__assistant-suggestion {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  margin-right: 0.5rem;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--border-action-high-blue-france);
  border-radius: 1rem;
  background: var(--background-alt-blue-france);
  color: var(--text-action-high-blue-france);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
}

.dossier-detail__icon-button {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 1px solid var(--border-default-grey);
  border-radius: 50%;
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  cursor: pointer;
}

.dossier-detail__icon-button:hover {
  background: var(--background-alt-grey-hover);
}

.dossier-details-modal__info {
  margin: 0 0 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.dossier-details-modal__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 0.625rem;
  border-bottom: 1px solid var(--border-default-grey);
}

.dossier-details-modal__row dt {
  color: var(--text-mention-grey);
  flex-shrink: 0;
}

.dossier-details-modal__row dd {
  margin: 0;
  text-align: right;
}

.dossier-details-modal__no-files {
  color: var(--text-mention-grey);
}

/* Section suggestions d'analyse (issue #54 : dossier « à ranger ») */
.dossier-detail__a-ranger-label {
  margin-left: 0.5rem;
  color: var(--text-mention-grey);
}

.dossier-detail__suggestions {
  margin-bottom: 1.5rem;
  flex-shrink: 0;
}

.dossier-detail__suggestions-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.dossier-detail__suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-top: 1rem;
}

.dossier-detail__suggestion-card {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.375rem;
  background: var(--background-default-grey);
}

.dossier-detail__suggestion-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.dossier-detail__suggestion-name {
  font-weight: 500;
}

.dossier-detail__suggestion-score {
  font-size: 0.875rem;
  color: var(--text-mention-grey);
  white-space: nowrap;
}

.dossier-detail__suggestion-rationale {
  margin: 0;
  color: var(--text-default-grey);
}
</style>
