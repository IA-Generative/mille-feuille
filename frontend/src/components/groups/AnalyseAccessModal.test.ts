import VueDsfr from "@gouvminint/vue-dsfr";
import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AnalyseAccessModal from "@/components/groups/AnalyseAccessModal.vue";
import { apiFetch } from "@/utils/api";

vi.mock("@/utils/api", () => ({ apiFetch: vi.fn(), userMessage: (e: Error) => e.message }));
// jsdom n'a pas ResizeObserver, dont la pop-up de l'application se sert.

const fetchMock = vi.mocked(apiFetch);
let canEdit = true;

const access = () => ({
  can_edit: canEdit,
  groups: [{ id: "g1", name: "Service culture", editable: canEdit }],
  available_groups: canEdit ? [{ id: "g2", name: "Sécurité routière" }] : [],
  people: [{ id: "p1", name: "Camille Durand", email: "", role_id: "r1", pending: false, editable: canEdit }],
  assignable_role_ids: ["r1"],
  versions: [],
});

const renderModal = async () => {
  render(AnalyseAccessModal, {
    props: { opened: true, analyseId: "a1" },
    global: { plugins: [VueDsfr], stubs: { VIcon: true } },
  });
  await screen.findByText("Camille Durand");
};

describe("AnalyseAccessModal", () => {
  beforeEach(() => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    canEdit = true;
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (path) =>
      (path.startsWith("/api/roles")
        ? [{ id: "r1", name: "Lecteur", description: "", permissions: [], system: false, in_use: true, assignable: true, versions: [] }]
        : access()) as never,
    );
  });

  it("envoie les groupes cochés, la personne gardée et la nouvelle adresse", async () => {
    await renderModal();

    await fireEvent.click(screen.getByRole("checkbox", { name: "Sécurité routière", hidden: true }));
    await fireEvent.update(screen.getByLabelText("Personne à ajouter"), "Externe@example.org");
    await fireEvent.click(screen.getByRole("button", { name: "Ajouter", hidden: true }));
    await fireEvent.click(screen.getByRole("button", { name: "Enregistrer", hidden: true }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(JSON.parse(String(init!.body))).toEqual({
      group_ids: ["g1", "g2"],
      people: [{ id: "p1", role_id: "r1" }, { email: "externe@example.org", role_id: "r1" }],
    });
  });

  it("est en lecture seule pour qui ne gère pas les accès", async () => {
    canEdit = false;
    await renderModal();

    expect(screen.queryByRole("button", { name: "Enregistrer", hidden: true })).toBeNull();
    expect(screen.queryByLabelText("Personne à ajouter")).toBeNull();
  });
});
