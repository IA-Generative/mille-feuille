import { describe, expect, it } from "vitest";

import BackLink from "@/components/BackLink.vue";

import { mountWithDsfr } from "./mount";

describe("mountWithDsfr", () => {
  it("résout <RouterLink> grâce au router mémoire", () => {
    const wrapper = mountWithDsfr(BackLink, { props: { to: "/" }, slots: { default: "Retour" } });

    const link = wrapper.get("a");
    expect(link.attributes("href")).toBe("/");
    expect(link.text()).toBe("Retour");
  });

  it("rend le vrai VIcon de vue-dsfr (plugin installé par vitest.setup.ts)", () => {
    const wrapper = mountWithDsfr(BackLink, { props: { to: "/" } });

    // Un composant non résolu serait rendu comme une balise <vicon> inconnue, sans <svg>.
    expect(wrapper.find("svg").exists()).toBe(true);
    expect(wrapper.find("vicon").exists()).toBe(false);
  });
});
