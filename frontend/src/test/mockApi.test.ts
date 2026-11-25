import { describe, expect, it } from "vitest";

import { ApiError } from "@/utils/api";

import { mockApi } from "./mockApi";

describe("mockApi", () => {
  it("fait échouer le test sur un appel non prévu", async () => {
    const { apiFetch } = await import("@/utils/api");
    await expect(apiFetch("/api/inconnu")).rejects.toThrow("apiFetch non simulé");
    // L'appel est signalé à l'afterEach de vitest.setup.ts, même si le code testé avait avalé l'erreur.
    expect(() => mockApi.assertNoUnexpectedCalls()).toThrow("GET /api/inconnu");
    mockApi.reset(); // on a provoqué l'appel exprès : on purge pour que l'afterEach ne le re-signale pas
  });

  it("renvoie la réponse prévue", async () => {
    mockApi.get("/api/me/stats", { documents: 3 });
    const { apiFetch } = await import("@/utils/api");
    expect(await apiFetch("/api/me/stats")).toEqual({ documents: 3 });
  });

  it("distingue les méthodes et enregistre le corps envoyé", async () => {
    mockApi.post("/api/notes", ({ body }: { body: unknown }) => ({ saved: body }));
    const { apiFetch } = await import("@/utils/api");

    const reply = await apiFetch("/api/notes", { method: "POST", body: JSON.stringify({ text: "a" }) });

    expect(reply).toEqual({ saved: { text: "a" } });
    expect(mockApi.calls).toEqual([{ method: "POST", path: "/api/notes", body: { text: "a" } }]);
    // Le même chemin en GET n'a pas été prévu.
    await expect(apiFetch("/api/notes")).rejects.toThrow("GET /api/notes");
    mockApi.reset();
  });

  it("simule une erreur serveur avec le vrai ApiError", async () => {
    mockApi.fail("GET", "/api/me/stats", 403, "Interdit");
    const { apiFetch } = await import("@/utils/api");

    const error = await apiFetch("/api/me/stats").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, message: "Interdit" });
  });
});
