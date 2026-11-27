import { mount, RouterLinkStub } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ConversationSearchResults from "@/components/conversationSearch/ConversationSearchResults.vue";
import type { ConversationSearchResult } from "@/types/conversation";

const found: ConversationSearchResult = {
  conversationId: "c1",
  dossierId: "d1",
  dossierName: "Aide au logement",
  date: new Date().toISOString(),
  match: {
    messageId: "m1",
    role: "assistant",
    excerpt: [
      { text: "Le ", highlighted: false },
      { text: "justificatif", highlighted: true },
      { text: " <b>manque</b>", highlighted: false },
    ],
  },
  matchCount: 3,
};

function render(props: Partial<InstanceType<typeof ConversationSearchResults>["$props"]> = {}) {
  return mount(ConversationSearchResults, {
    props: { results: [found], total: 1, status: "ready", ...props },
    global: { stubs: { RouterLink: RouterLinkStub } },
  });
}

describe("ConversationSearchResults", () => {
  it("shows the dossier, who wrote it, the highlighted words and the other messages", () => {
    const wrapper = render();

    expect(wrapper.findComponent(RouterLinkStub).props("to")).toEqual({ path: "/dossiers/d1", query: { message: "m1" } });
    expect(wrapper.text()).toContain("Aide au logement");
    expect(wrapper.text()).toContain("Assistant :");
    expect(wrapper.find("mark").text()).toBe("justificatif");
    expect(wrapper.text()).toContain("et 2 autres messages");
    // Le texte d'un message n'est jamais interprété comme du HTML.
    expect(wrapper.find("b").exists()).toBe(false);
  });

  it("says when only the dossier name matched", () => {
    const wrapper = render({ results: [{ ...found, match: null, matchCount: 0 }] });

    expect(wrapper.text()).toContain("Trouvé dans le nom du dossier");
    expect(wrapper.findComponent(RouterLinkStub).props("to")).toEqual({ path: "/dossiers/d1", query: {} });
  });

  it("announces loading, no result and failure", async () => {
    const wrapper = render({ results: [], total: 0, status: "loading" });
    expect(wrapper.find('[role="status"]').text()).toBe("Recherche…");

    await wrapper.setProps({ status: "ready" });
    expect(wrapper.find('[role="status"]').text()).toBe("Aucune conversation trouvée.");

    await wrapper.setProps({ status: "error" });
    await wrapper.find("button").trigger("click");
    expect(wrapper.emitted("retry")).toHaveLength(1);
  });

  it("offers to show more results", async () => {
    const wrapper = render({ total: 25 });

    await wrapper.find("button").trigger("click");

    expect(wrapper.emitted("more")).toHaveLength(1);
  });
});
