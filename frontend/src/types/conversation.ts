export type MessageRole = "user" | "assistant";

export type FeedbackValue = "up" | "down";

export type FeedbackReasonCode =
  | "incorrect_answer"
  | "not_useful"
  | "questionable_sources"
  | "inappropriate_tone"
  | "other";

export const FEEDBACK_REASON_LABELS: Record<FeedbackReasonCode, string> = {
  incorrect_answer: "Réponse incorrecte",
  not_useful: "Pas utile",
  questionable_sources: "Sources douteuses",
  inappropriate_tone: "Ton inapproprié",
  other: "Autre",
};

export interface Feedback {
  id: string;
  messageId: string;
  value: FeedbackValue;
  reasons: FeedbackReasonCode[];
  comment: string | null;
  createdAt: string;
}

export interface MessageSource {
  id: string;
  dossierDocumentId: string | null;
  executionStepId: string | null;
  excerpt: string | null;
  pages: { id: string; pageNumber: number }[];
  /** Zones normalisées (0-1, origine en haut à gauche) citées, rattachées à leur page. */
  boundingBoxes: SourceBoundingBox[];
}

export interface SourceBoundingBox {
  id: string;
  pageId: string;
  xMin: number;
  yMin: number;
  xMax: number;
  yMax: number;
}

/** Une question à choix de l'assistant (arguments de l'appel `ask_user`). */
export interface ToolQuestion {
  question: string;
  header: string;
  multiSelect: boolean;
  options: { label: string; description: string }[];
}

/** La réponse à une question : des options proposées et/ou un texte libre. */
export interface QuestionAnswer {
  selected: string[];
  other?: string;
}

/** Où en est la demande d'autorisation d'un outil qui modifie des données. */
export type ToolCallStatus = "pending" | "approved" | "refused" | "executed" | "superseded";

/** Un appel d'outil demandé par l'assistant dans un message, avec les arguments exacts qui seront exécutés. */
export interface ChatToolCall {
  id: string;
  /** « ask_user » pour une question à choix de l'assistant, sinon l'outil appelé. */
  toolId: string;
  toolName: string;
  serverName: string;
  args: Record<string, unknown>;
  /** Il modifie des données : l'assistant attend l'accord de la personne. */
  sideEffect: boolean;
  status: ToolCallStatus;
}

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  sources: MessageSource[];
  feedback: Feedback | null;
  toolCalls: ChatToolCall[];
}

/** Chat de la page dossier : une conversation par (dossier, utilisateur). */
export interface Conversation {
  id: string;
  dossierId: string;
  userId: string;
  createdAt: string;
  /** Identifiant de modèle (voir GET /api/models) ; null = pas de préférence, le hub par défaut sera utilisé. */
  model: string | null;
}

/** Entrée de la liste "mes conversations" dans la sidebar, façon ChatGPT. */
export interface ConversationSummary {
  id: string;
  dossierId: string;
  dossierName: string;
  lastMessagePreview?: string;
  lastActivityAt: string;
}

// --- Événements de chat (streaming de l'exécution) ---

export type ChatEventKind = "tool_call" | "tool_result" | "thinking" | "done" | "error";

export interface ChatEvent {
  id: string;
  conversationId: string;
  kind: ChatEventKind;
  data: Record<string, unknown>;
  createdAt: string;
}
