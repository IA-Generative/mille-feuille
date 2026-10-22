import { ref } from "vue";

import { apiFetch } from "@/utils/api";
import type {
  ChatEvent,
  Conversation,
  Feedback,
  FeedbackReasonCode,
  FeedbackValue,
  Message,
  MessageSource,
  ChatToolCall,
  QuestionAnswer,
} from "@/types/conversation";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

function mapFeedback(api: any): Feedback | null {
  if (!api) return null;
  return {
    id: api.id,
    messageId: api.message_id,
    value: api.value,
    reasons: api.reasons,
    comment: api.comment,
    createdAt: api.created_at,
  };
}

function mapSource(api: any): MessageSource {
  return {
    id: api.id,
    dossierDocumentId: api.dossier_document_id,
    executionStepId: api.execution_step_id,
    excerpt: api.excerpt,
    pages: (api.pages ?? []).map((p: any) => ({ id: p.id, pageNumber: p.page_number })),
    boundingBoxes: (api.bounding_boxes ?? []).map((b: any) => ({
      id: b.id,
      pageId: b.document_page_id,
      xMin: b.x_min,
      yMin: b.y_min,
      xMax: b.x_max,
      yMax: b.y_max,
    })),
  };
}

function mapToolCall(api: any): ChatToolCall {
  return {
    id: api.id,
    toolId: api.tool_id,
    toolName: api.tool_name,
    serverName: api.server_name,
    args: api.arguments ?? {},
    sideEffect: api.side_effect,
    status: api.status,
  };
}

function mapMessage(api: any): Message {
  return {
    id: api.id,
    role: api.role,
    content: api.content,
    createdAt: api.created_at,
    sources: (api.sources ?? []).map(mapSource),
    feedback: mapFeedback(api.feedback),
    toolCalls: (api.tool_calls ?? []).map(mapToolCall),
  };
}

const MESSAGES_PAGE_SIZE = 20;

function mapConversation(api: any): Conversation {
  return {
    id: api.id,
    dossierId: api.dossier_id,
    userId: api.user_id,
    createdAt: api.created_at,
    model: api.model,
  };
}

// Chat de la page dossier : une conversation par (dossier, utilisateur
// courant). Instancié par dossier, contrairement à useAnalyses/useDossiers
// qui sont des stores partagés par toute l'application.
export function useConversations(dossierId: string) {
  const conversation = ref<Conversation | undefined>(undefined);
  // Messages chargés par pages (curseur) : les plus récents d'abord, les
  // plus anciens à la demande quand l'utilisateur remonte dans la discussion.
  const messages = ref<Message[]>([]);
  const hasMoreMessages = ref(false);
  const isLoadingMore = ref(false);

  const messagesUrl = (conversationId: string) =>
    `/api/dossiers/${dossierId}/conversations/${conversationId}/messages`;

  const fetchMessagesPage = async (conversationId: string, before?: string) => {
    const query = new URLSearchParams({ limit: String(MESSAGES_PAGE_SIZE) });
    if (before) query.set("before", before);
    const data = await apiFetch<{ items: any[]; has_more: boolean }>(
      `${messagesUrl(conversationId)}?${query.toString()}`,
    );
    return { items: data.items.map(mapMessage), hasMore: data.has_more };
  };

  // GET /conversations est paginé ({ items, total, ... }) : on lit `items`.
  const listConversations = async (): Promise<any[]> => {
    const data = await apiFetch<{ items: any[] }>(`/api/dossiers/${dossierId}/conversations?page_size=100`);
    return data.items;
  };

  // Garde contre les appels concurrents : si ensureConversation() est
  // appelé plusieurs fois avant la résolution du premier appel (ex:
  // onMounted + sendMessage), on réutilise la même promesse au lieu de
  // déclencher plusieurs créations de conversation.
  let pending: Promise<Conversation> | undefined;

  const ensureConversation = async (): Promise<Conversation> => {
    if (conversation.value) return conversation.value;
    if (pending) return pending;

    pending = (async () => {
      const existing = await listConversations();
      if (existing.length > 0) {
        conversation.value = mapConversation(existing[0]);
      } else {
        const created = await apiFetch<any>(`/api/dossiers/${dossierId}/conversations`, { method: "POST" });
        conversation.value = mapConversation(created);
      }
      const page = await fetchMessagesPage(conversation.value!.id);
      messages.value = page.items;
      hasMoreMessages.value = page.hasMore;
      return conversation.value!;
    })().finally(() => {
      pending = undefined;
    });

    return pending;
  };

  const sendMessage = async (content: string) => {
    const current = await ensureConversation();
    const data = await apiFetch<any>(messagesUrl(current.id), {
      method: "POST",
      body: JSON.stringify({ content }),
    });
    messages.value.push(mapMessage(data));
  };

  // Décide d'un lot de demandes d'outils (toutes ensemble) : le chat est relancé, il exécute ce qui est autorisé puis
  // reprend là où il s'était arrêté. L'appelant suit alors la nouvelle exécution (flux SSE).
  const decideToolCalls = async (decisions: { id: string; allow: boolean; comment?: string }[]) => {
    const current = await ensureConversation();
    const data = await apiFetch<any[]>(`/api/dossiers/${dossierId}/conversations/${current.id}/tool-calls/decisions`, {
      method: "POST",
      body: JSON.stringify({ decisions }),
    });
    const decided = data.map(mapToolCall);
    for (const message of messages.value) {
      message.toolCalls = message.toolCalls.map((call) => decided.find((d) => d.id === call.id) ?? call);
    }
  };

  // Répond à une question à choix de l'assistant (une réponse par question) : le chat est relancé, il lit la réponse comme
  // le résultat de sa question. L'appelant suit alors la nouvelle exécution (flux SSE).
  const answerToolQuestion = async (callId: string, answers: QuestionAnswer[]) => {
    const current = await ensureConversation();
    const data = await apiFetch<any>(
      `/api/dossiers/${dossierId}/conversations/${current.id}/tool-calls/${callId}/answer`,
      { method: "POST", body: JSON.stringify({ answers }) },
    );
    const answered = mapToolCall(data);
    for (const message of messages.value) {
      message.toolCalls = message.toolCalls.map((call) => (call.id === answered.id ? answered : call));
    }
  };

  // Charge la page de messages plus anciens (défilement vers le haut).
  const loadOlderMessages = async () => {
    const current = conversation.value;
    const oldest = messages.value[0];
    if (!current || !oldest || !hasMoreMessages.value || isLoadingMore.value) return;
    isLoadingMore.value = true;
    try {
      const page = await fetchMessagesPage(current.id, oldest.id);
      messages.value = [...page.items, ...messages.value];
      hasMoreMessages.value = page.hasMore;
    } finally {
      isLoadingMore.value = false;
    }
  };

  // SSE : s'abonne au flux d'événements de chat (tool_call, tool_result,
  // done, error) pendant que le worker exécute le graphe LangGraph. Le
  // callback reçoit chaque événement au fur et à mesure, et onEventDone est
  // appelé quand l'exécution est terminée (le frontend peut alors
  // recharger la conversation pour récupérer le message assistant final).
  const streamConversation = (
    conversationId: string,
    onEvent: (event: ChatEvent) => void,
    onDone: () => void,
  ): (() => void) => {
    const url = `${API_BASE_URL}/api/dossiers/${dossierId}/conversations/${conversationId}/stream`;
    const eventSource = new EventSource(url, { withCredentials: true });

    eventSource.addEventListener("chat-event", (event) => {
      const data = JSON.parse(event.data);
      onEvent(data);
    });
    eventSource.addEventListener("done", () => {
      eventSource.close();
      onDone();
    });
    eventSource.addEventListener("error", () => {
      eventSource.close();
    });

    return () => eventSource.close();
  };

  // Recharge la page la plus récente (message assistant final avec ses
  // sources, après la fin du streaming) en conservant les pages plus
  // anciennes déjà chargées par le défilement.
  const refreshConversation = async () => {
    const current = conversation.value;
    if (!current) return;
    const page = await fetchMessagesPage(current.id);
    const firstCreatedAt = page.items[0]?.createdAt;
    const older = firstCreatedAt ? messages.value.filter((m) => m.createdAt < firstCreatedAt) : [];
    messages.value = [...older, ...page.items];
    if (older.length === 0) hasMoreMessages.value = page.hasMore;
  };

  // Supprime uniquement la conversation (et ses messages) : le dossier, ses
  // documents et l'analyse associée ne sont pas touchés.
  const deleteConversation = async () => {
    const current = conversation.value;
    if (!current) return;
    await apiFetch(`/api/dossiers/${dossierId}/conversations/${current.id}`, { method: "DELETE" });
    conversation.value = undefined;
    messages.value = [];
    hasMoreMessages.value = false;
  };

  const setModel = async (model: string | null) => {
    const current = await ensureConversation();
    const data = await apiFetch<any>(`/api/dossiers/${dossierId}/conversations/${current.id}/model`, {
      method: "PUT",
      body: JSON.stringify({ model }),
    });
    conversation.value = mapConversation(data);
  };

  const replaceMessage = (updated: Message) => {
    const index = messages.value.findIndex((m) => m.id === updated.id);
    if (index !== -1) messages.value.splice(index, 1, updated);
  };

  const setFeedback = async (
    messageId: string,
    value: FeedbackValue,
    reasons: FeedbackReasonCode[] = [],
    comment: string | null = null,
  ) => {
    const current = await ensureConversation();
    const data = await apiFetch<any>(`${messagesUrl(current.id)}/${messageId}/feedback`, {
      method: "PUT",
      body: JSON.stringify({ value, reasons, comment }),
    });
    replaceMessage(mapMessage(data));
  };

  const removeFeedback = async (messageId: string) => {
    const current = await ensureConversation();
    const data = await apiFetch<any>(`${messagesUrl(current.id)}/${messageId}/feedback`, { method: "DELETE" });
    replaceMessage(mapMessage(data));
  };

  return {
    conversation,
    messages,
    hasMoreMessages,
    isLoadingMore,
    loadOlderMessages,
    ensureConversation,
    sendMessage,
    decideToolCalls,
    answerToolQuestion,
    streamConversation,
    refreshConversation,
    deleteConversation,
    setModel,
    setFeedback,
    removeFeedback,
  };
}
