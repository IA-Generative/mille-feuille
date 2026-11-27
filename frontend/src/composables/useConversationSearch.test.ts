import { effectScope, nextTick } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SEARCH_DELAY_MS, useConversationSearch } from "@/composables/useConversationSearch";
import { apiFetch } from "@/utils/api";

vi.mock("@/utils/api", () => ({ apiFetch: vi.fn() }));

const fetchMock = vi.mocked(apiFetch);

function result(id: string) {
  return { conversation_id: id, dossier_id: `d-${id}`, dossier_name: `Dossier ${id}`, date: "2026-11-27T10:00:00Z", match: null, match_count: 0 };
}

function setup() {
  const scope = effectScope();
  return { scope, search: scope.run(() => useConversationSearch())! };
}

async function type(search: ReturnType<typeof useConversationSearch>, text: string) {
  search.query.value = text;
  await nextTick();
  await vi.advanceTimersByTimeAsync(SEARCH_DELAY_MS);
}

describe("useConversationSearch", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock.mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("sends the words in the body, once the person stops typing", async () => {
    fetchMock.mockResolvedValue({ items: [result("1")], total: 1 });
    const { search } = setup();

    search.query.value = "ju";
    await nextTick();
    await type(search, "  justificatif ");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/conversations/search", {
      method: "POST",
      body: JSON.stringify({ query: "justificatif", page: 1, page_size: 20 }),
    });
    expect(search.results.value[0].dossierName).toBe("Dossier 1");
    expect(search.status.value).toBe("ready");
  });

  it("does not search with a single character", async () => {
    const { search } = setup();

    await type(search, "a");

    expect(search.active.value).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("ignores a late answer to older words", async () => {
    let answerOld: (value: unknown) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)));
    fetchMock.mockResolvedValueOnce({ items: [result("new")], total: 1 });
    const { search } = setup();

    await type(search, "ancien");
    await type(search, "nouveau");
    answerOld({ items: [result("old")], total: 1 });
    await vi.runAllTimersAsync();

    expect(search.results.value.map((r) => r.conversationId)).toEqual(["new"]);
  });

  it("adds the next page and retries the one that failed", async () => {
    fetchMock.mockResolvedValueOnce({ items: [result("1")], total: 2 });
    fetchMock.mockRejectedValueOnce(new Error("réseau"));
    fetchMock.mockResolvedValueOnce({ items: [result("2")], total: 2 });
    const { search } = setup();

    await type(search, "mot");
    await search.loadMore();
    expect(search.status.value).toBe("error");
    expect(search.results.value).toHaveLength(1);

    await search.retry();
    expect(search.results.value.map((r) => r.conversationId)).toEqual(["1", "2"]);
    expect(JSON.parse(fetchMock.mock.calls[2][1]!.body as string).page).toBe(2);
  });
});
