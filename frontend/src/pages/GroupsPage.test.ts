import VueDsfr from "@gouvminint/vue-dsfr";
import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import GroupsPage from "@/pages/GroupsPage.vue";
import { apiFetch } from "@/utils/api";

const auth = vi.hoisted(() => ({ isAdmin: false }));
vi.mock("@/composables/useAuth", () => ({ useAuth: () => ({ isAdmin: ref(auth.isAdmin) }) }));
vi.mock("@/utils/api", () => ({ apiFetch: vi.fn(), userMessage: (e: Error) => e.message }));

const fetchMock = vi.mocked(apiFetch);
let manages = true;

const group = () => ({
  id: "g1", name: "Service culture", description: "", member_count: 1,
  can_manage_members: manages, deletable: false, versions: [],
});
const role = (id: string, name: string, assignable: boolean) => ({
  id, name, description: "", permissions: ["dossier.view"], system: false, in_use: true, assignable, versions: [],
});
const member = () => ({
  id: "m1", user_id: null, name: "", email: "futur@example.org", role_id: "r1", pending: true, editable: manages,
});

function answer(path: string, init?: RequestInit): unknown {
  if (init?.method === "POST") return {};
  if (path === "/api/groups") return [group()];
  if (path.startsWith("/api/roles")) return [role("r0", "Admin de groupe", false), role("r1", "Instructeur", true)];
  if (path.endsWith("/members")) return [member()];
  if (path.endsWith("/events")) return [];
  if (path.startsWith("/api/users")) return [{ id: "u7", name: "Camille Durand" }];
  throw new Error(path);
}

const renderPage = async () => {
  render(GroupsPage, { global: { plugins: [VueDsfr], stubs: { VIcon: true } } });
  await screen.findByText("futur@example.org");
};
const add = async (value: string) => {
  await fireEvent.update(screen.getByLabelText("Personne à ajouter"), value);
  await fireEvent.click(screen.getByRole("button", { name: "Ajouter" }));
};
const posted = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(String(init!.body)));

describe("GroupsPage", () => {
  beforeEach(() => {
    auth.isAdmin = false;
    manages = true;
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (path, init) => answer(path, init) as never);
  });

  it("réserve la création de groupe aux super admins", async () => {
    await renderPage();

    expect(screen.queryByRole("button", { name: "Créer un groupe" })).toBeNull();
    expect(screen.getByText("En attente de connexion")).toBeTruthy();
  });

  it("ne propose que les rôles qu'on peut attribuer", async () => {
    await renderPage();

    expect(screen.queryByRole("option", { name: "Admin de groupe" })).toBeNull();
  });

  it("montre les membres en lecture seule à qui ne les gère pas", async () => {
    manages = false;
    await renderPage();

    expect(screen.queryByRole("button", { name: "Ajouter" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Retirer/ })).toBeNull();
  });

  it("ajoute une adresse, ou une personne choisie par son nom", async () => {
    await renderPage();

    await add("autre@example.org");
    await waitFor(() => expect(posted()).toEqual([{ email: "autre@example.org", role_id: "r1" }]));
    await fireEvent.update(screen.getByLabelText("Personne à ajouter"), "Camille Durand");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/users?limit=10&q=Camille%20Durand"));
    await add("Camille Durand");
    await waitFor(() => expect(posted()[1]).toEqual({ user_id: "u7", role_id: "r1" }));
  });
});
