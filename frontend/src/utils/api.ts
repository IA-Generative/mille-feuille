// Le navigateur parle directement au backend via l'ingress (même host) :
// le cookie de session du BFF est scopé à cette origine, et le CORS du
// backend autorise explicitement le frontend (voir KeycloakSettings.FRONTEND_URL).
// En dev local, VITE_API_BASE_URL peut pointer vers http://localhost:8000.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Détail brut renvoyé par le serveur (texte, liste d'erreurs ou objet structuré, ex. rapport de validation). */
    public detail?: unknown,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isFormData = init.body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: isFormData ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    // Un détail structuré (`{code, message}`) donne son message ; sinon le libellé HTTP.
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : // Erreur de validation FastAPI : le premier message, sans le préfixe technique de Pydantic.
            typeof detail?.[0]?.msg === "string"
            ? detail[0].msg.replace(/^Value error, /, "")
            : response.statusText;
    throw new ApiError(response.status, message, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// Messages bruts que le serveur ou le proxy renvoient quand personne n'a écrit de vrai message.
const GENERIC = /^(Not Found|Forbidden|Not authenticated|Method Not Allowed|Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)$/i;

/** Une phrase française pour l'utilisateur : ce qui n'a pas marché et ce qu'il peut faire. */
export function userMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) {
    // fetch() qui échoue (réseau coupé, CORS) lève un TypeError au texte anglais du navigateur.
    return error instanceof TypeError
      ? "Impossible de joindre le serveur. Vérifiez votre connexion puis réessayez."
      : fallback;
  }
  // Un vrai message du backend (« Analyse introuvable », 422 {code, message}…) est déjà lisible : on le garde.
  if (error.message !== "" && !GENERIC.test(error.message)) return error.message;
  if (error.status === 401) return "Votre session a expiré. Reconnectez-vous pour continuer.";
  if (error.status === 403) return "Vous n'avez pas les droits pour afficher cette section.";
  if (error.status === 404)
    return "Cette section est introuvable. Elle a peut-être été supprimée, ou vous n'y avez pas accès.";
  return `${fallback} Réessayez dans un instant ; si le problème continue, contactez l'équipe.`;
}