import VueDsfr from "@gouvminint/vue-dsfr";
import { fireEvent, render, screen } from "@testing-library/vue";
import { beforeEach, describe, expect, it } from "vitest";

import { resetMockGroups } from "@/composables/useGroups";
import GroupsPage from "@/pages/GroupsPage.vue";

const renderPage = () => render(GroupsPage, { global: { plugins: [VueDsfr], stubs: { VIcon: true } } });
const viewAs = (id: string) => fireEvent.update(screen.getByRole("combobox", { name: /voir en tant que/i }), id);

describe("GroupsPage (maquette)", () => {
  beforeEach(resetMockGroups);

  it("laisse le super admin créer un groupe", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "Créer un groupe" })).toBeTruthy();
    expect(screen.getByText(/rien n'est enregistré/)).toBeTruthy();
  });

  it("masque ce que l'admin d'un groupe ne peut pas faire", async () => {
    renderPage();
    await viewAs("admin");

    expect(screen.queryByRole("button", { name: "Créer un groupe" })).toBeNull();
    expect(screen.getByRole("button", { name: "Ajouter" })).toBeTruthy();
    expect(screen.queryByText("Sécurité routière")).toBeNull();
  });

  it("montre les membres en lecture seule aux autres", async () => {
    renderPage();
    await viewAs("member");

    expect(screen.queryByRole("button", { name: "Ajouter" })).toBeNull();
    expect(screen.getByText("En attente de première connexion")).toBeTruthy();
  });

  it("ajoute une adresse en attente de première connexion", async () => {
    renderPage();
    await fireEvent.update(screen.getByLabelText("Adresse e-mail à ajouter"), "autre@example.org");
    await fireEvent.click(screen.getByRole("button", { name: "Ajouter" }));

    expect(screen.getAllByText("autre@example.org").length).toBe(1);
  });
});
