import { ApiError } from "@/utils/api";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Reply = unknown | ((call: { path: string; init: RequestInit; body: unknown }) => unknown);
interface Route { method: Method; path: string | RegExp; reply?: Reply; error?: ApiError }
interface Call { method: Method; path: string; body: unknown }

interface State { routes: Route[]; calls: Call[]; unexpected: string[] }
const g = globalThis as typeof globalThis & { __apiMock?: State };
const state = (g.__apiMock ??= { routes: [], calls: [], unexpected: [] });

/** Appelé par le vi.mock de vitest.setup.ts à la place de apiFetch. */
export async function dispatch(path: string, init: RequestInit = {}) {
  const method = (init.method ?? "GET").toUpperCase() as Method;
  const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
  state.calls.push({ method, path, body });

  const route = state.routes.find(
    (r) => r.method === method && (typeof r.path === "string" ? r.path === path : r.path.test(path)),
  );
  if (!route) {
    const msg = `apiFetch non simulé : ${method} ${path}`;
    state.unexpected.push(msg); // revérifié en afterEach : un catch applicatif ne peut pas l'étouffer
    throw new Error(msg);
  }
  if (route.error) throw route.error;
  return typeof route.reply === "function" ? route.reply({ path, init, body }) : route.reply;
}

export const mockApi = {
  on(method: Method, path: string | RegExp, reply?: Reply) {
    state.routes.push({ method, path, reply });
    return mockApi;
  },
  get: (path: string | RegExp, reply?: Reply) => mockApi.on("GET", path, reply),
  post: (path: string | RegExp, reply?: Reply) => mockApi.on("POST", path, reply),
  fail(method: Method, path: string | RegExp, status: number, message = "", detail?: unknown) {
    state.routes.push({ method, path, error: new ApiError(status, message, detail) });
    return mockApi;
  },
  get calls() { return state.calls; },
  reset() { state.routes.length = 0; state.calls.length = 0; state.unexpected.length = 0; },
  assertNoUnexpectedCalls() {
    if (state.unexpected.length) throw new Error(state.unexpected.join("\n"));
  },
};