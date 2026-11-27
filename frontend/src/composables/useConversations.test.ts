import { beforeEach, describe, expect, it, vi } from "vitest";

import { useConversations } from "@/composables/useConversations";
import { apiFetch } from "@/utils/api";

vi.mock("@/utils/api", () => ({ apiFetch: vi.fn(), API_BASE_URL: "" }));

const fetchMock = vi.mocked(apiFetch);

const message = (id: number) => ({ id: `m${id}`, role: "user", content: `Message ${id}`, created_at: `2026-11-27T10:00:${id}`, sources: [] });

/** Une conversation de trois pages d'un message : m3 (le plus récent), puis m2, puis m1. */
function serve() {
  fetchMock.mockImplementation(async (path: string) => {
    if (path.includes("/messages?")) {
      const before = new URL(path, "http://x").searchParams.get("before");
      const id = before ? Number(before.slice(1)) - 1 : 3;
      return { items: [message(id)], has_more: id > 1 };
    }
    return { items: [{ id: "c1", dossier_id: "d1", user_id: "u1", created_at: "2026-11-27T10:00:00", model: null }] };
  });
}

const pageCalls = () => fetchMock.mock.calls.filter(([path]) => String(path).includes("/messages?"));

describe("useConversations, remonter jusqu'à un message", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    serve();
  });

  it("loads older pages until the message is there", async () => {
    const { messages, loadUntil } = useConversations("d1");

    expect(await loadUntil("m1")).toBe(true);
    expect(messages.value.map((m) => m.id)).toEqual(["m1", "m2", "m3"]);
  });

  it("loads nothing more when the message is already there", async () => {
    const { loadUntil } = useConversations("d1");

    expect(await loadUntil("m3")).toBe(true);
    expect(pageCalls()).toHaveLength(1);
  });

  it("stops at the beginning when the message does not exist anymore", async () => {
    const { loadUntil, hasMoreMessages } = useConversations("d1");

    expect(await loadUntil("m9")).toBe(false);
    expect(hasMoreMessages.value).toBe(false);
  });

  it("waits for the first load and never loads a page twice", async () => {
    const { messages, ensureConversation, loadUntil, loadOlderMessages } = useConversations("d1");

    const first = ensureConversation();
    const found = loadUntil("m1");
    await first;
    await Promise.all([found, loadOlderMessages()]);

    expect(messages.value.map((m) => m.id)).toEqual(["m1", "m2", "m3"]);
    expect(pageCalls()).toHaveLength(3);
  });
});
