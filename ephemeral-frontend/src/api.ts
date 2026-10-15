import { API_BASE_URL } from "@/config";

// Même contrat que le frontend principal : cookie de session du BFF (HttpOnly) posé par le backend.
export { API_BASE_URL };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
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
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.[0]?.msg === "string"
          ? detail[0].msg.replace(/^Value error, /, "")
          : response.statusText;
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Lit une image servie par le backend (protégée par le cookie de session, donc pas un simple `<img src>`). */
export async function apiFetchBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.blob();
}
