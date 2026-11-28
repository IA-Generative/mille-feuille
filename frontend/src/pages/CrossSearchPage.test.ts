import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import VueDsfr from "@gouvminint/vue-dsfr";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

import CriteriaEditor from "@/components/crossSearch/CriteriaEditor.vue";
import { MOCK_DOSSIERS, MOCK_ITEMS } from "@/composables/mockCrossSearch";
import { allOfKind } from "@/composables/mockEntityCatalog";
import { mockResemblances, useResemblances } from "@/composables/useResemblances";
import CrossSearchPage from "@/pages/CrossSearchPage.vue";
import { mockApi } from "@/test/mockApi";
import { SHARED_KINDS, type CrossSearchResult } from "@/types/crossSearch";
import { ApiError } from "@/utils/api";
import { layoutClusters } from "@/utils/clusterLayout";
import { buildLinkGraph, highlightOf, restrictToKinds } from "@/utils/linkGraph";

const auth = vi.hoisted(() => ({ isAdmin: false }));
vi.mock("@/composables/useAuth", () => ({ useAuth: () => ({ isAdmin: ref(auth.isAdmin) }) }));
// sigma.js a besoin de WebGL, absent de jsdom.
vi.mock("@/components/crossSearch/ClusterGraph.vue", () => ({ default: { template: "<div />" } }));
vi.mock("@/components/crossSearch/LinkGraph.vue", () => ({ default: { template: "<div />" } }));

async function renderPage(url = "/recherche") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/recherche", component: CrossSearchPage },
      { path: "/dossiers/:id", name: "dossier-detail", component: { template: "<div />" } },
    ],
  });
  await router.push(url);
  const view = render(CrossSearchPage, { global: { plugins: [VueDsfr, router], stubs: { VIcon: true } } });
  return { ...view, router };
}

async function searchFor(query: string) {
  await fireEvent.update(screen.getByRole("searchbox"), query);
  await fireEvent.click(screen.getByRole("button", { name: /rechercher/i }));
}

const dossier = (id: string, name: string) => ({
  id,
  reference: `DOS-2026-${id}`,
  name,
  analyse_name: "Titre de séjour",
  theme_name: null,
  excerpts: [
    { document_name: "bail.pdf", page: 2, field: null, segments: [{ text: "lilas", highlighted: true }] },
  ],
});

const proof = (dossierId: string) => ({
  dossier_id: dossierId,
  document_name: "demande.pdf",
  page: 1,
  text: "12 rue des Lilas",
  origin: "Analyse Titre de séjour · Adresse",
});

const sharedAddress = {
  id: "value:1",
  kind: "value",
  label: "12 rue des Lilas",
  dossier_ids: ["a", "b"],
  occurrences: [proof("a"), proof("b")],
};

const FOUND = { dossiers: [dossier("a", "Camille"), dossier("b", "Sacha")], total: 2, items: [sharedAddress] };
const LINKS = { anchor_ids: ["a"], dossiers: [dossier("a", "Camille"), dossier("b", "Sacha")], items: [sharedAddress] };

/** Un résultat construit sur les données fictives, pour les fonctions du graphe. */
const graphResult = (anchorIds: string[] = []): CrossSearchResult => ({
  query: "",
  anchorIds,
  dossiers: MOCK_DOSSIERS,
  items: MOCK_ITEMS,
  hidden: [],
});

describe("buildLinkGraph", () => {
  it("retire les types décochés sans retirer les dossiers", () => {
    const result = graphResult();
    const graph = buildLinkGraph(result, []);

    expect(graph.nodes.filter((n) => n.type === "item")).toEqual([]);
    expect(graph.nodes.filter((n) => n.type === "dossier")).toHaveLength(result.dossiers.length);
    const ids = new Set(graph.nodes.map((n) => n.id));
    expect(graph.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  });

  it("garde les dossiers choisis quand un filtre retire les autres", () => {
    expect(restrictToKinds(graphResult(["d2"]), []).dossiers.map((d) => d.id)).toEqual(["d2"]);
  });
});

describe("highlightOf", () => {
  const graph = buildLinkGraph(graphResult(), SHARED_KINDS.map((k) => k.value));

  it("met en avant le trait choisi seul", () => {
    const link = highlightOf(graph, { type: "link", dossierId: "d1", targetId: "a-lilas" })!;
    expect([...link.nodes].sort()).toEqual(["a-lilas", "d1"]);
  });
});

const { rules, saveRule, restoreRule, removeRule } = useResemblances();
const ruleById = (id: string) => rules.value.find((r) => r.id === id)!;
const dossiersOf = (id: string) => mockResemblances(ruleById(id)).map((g) => [...g.dossierIds].sort());

describe("thèmes de ressemblance", () => {
  it("applique la portée : au sein d'un thème d'analyse, ou entre thèmes", () => {
    expect(dossiersOf("person-within")).toEqual([["d3", "d4", "d7"]]);
    expect(dossiersOf("person-across")).toEqual([
      ["d1", "d3", "d4", "d7"],
      ["d5", "d6"],
    ]);
  });

  it("exige tous les critères à la fois", () => {
    expect(dossiersOf("driver-company")).toEqual([["d1", "d4"]]);
  });

  it("garde l'historique et sait restaurer", () => {
    const draft = { name: "Essai", description: "", criteria: [allOfKind("company", "Entreprise")], scope: "all" as const, certainty: "probable" as const, active: true };
    const id = saveRule(draft);
    saveRule({ ...draft, scope: "across" }, id);
    expect(ruleById(id).versions).toHaveLength(1);

    restoreRule(id, ruleById(id).versions[0]!.id);
    expect(ruleById(id).scope).toBe("all");
    expect(ruleById(id).versions).toHaveLength(2);
    removeRule(id);
  });
});

describe("critères d'un thème de ressemblance", () => {
  it("ne compare que les dossiers des analyses dont il cite des entités", () => {
    const id = saveRule({
      name: "Numéro de permis",
      description: "",
      criteria: [{ id: "c", origin: "analysis", name: "Numéro", entityIds: ["Permis de conduire › Numéro de permis"] }],
      scope: "all",
      certainty: "identical",
      active: true,
    });
    expect(dossiersOf(id)).toEqual([["d3", "d7"]]);
    removeRule(id);
  });

  it("ajoute une entité des analyses, puis une entité personnalisée", async () => {
    const view = render(CriteriaEditor, {
      props: { modelValue: [], "onUpdate:modelValue": (value: unknown) => view.rerender({ modelValue: value }) },
    });

    await fireEvent.update(screen.getByLabelText("Ajouter depuis les entités des analyses"), "Licence de transport › Gérant");
    expect(screen.getByRole("button", { name: "Retirer le critère Gérant" })).toBeTruthy();
    expect(screen.getByText("Analyse Licence de transport")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Entité personnalisée" }));
    await fireEvent.update(screen.getByLabelText("Nom de l'entité"), "Numéro de châssis");
    await fireEvent.click(screen.getByRole("button", { name: "Ajouter ce critère" }));
    expect(screen.getByRole("button", { name: "Retirer le critère Numéro de châssis" })).toBeTruthy();
    expect(screen.getByText("Manuel")).toBeTruthy();
  });
});

describe("layoutClusters", () => {
  it("fait un amas par groupe, sans que les amas se touchent", () => {
    const groups = mockResemblances(ruleById("person-across"));
    const { nodes, clusters } = layoutClusters(groups);

    expect(clusters.map((c) => c.groupId)).toEqual(groups.map((g) => g.id));
    for (const node of nodes) {
      const cluster = clusters.find((c) => c.groupId === node.groupId)!;
      expect(Math.hypot(node.x - cluster.x, node.y - cluster.y)).toBeLessThan(cluster.radius);
    }
    clusters.forEach((a, i) =>
      clusters.slice(i + 1).forEach((b) => expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(a.radius + b.radius)),
    );
  });
});

describe("CrossSearchPage", () => {
  it("réserve la définition des thèmes aux administrateurs", async () => {
    const first = await renderPage();
    await fireEvent.click(screen.getByLabelText("Rapprochements"));
    expect(screen.queryByRole("button", { name: "Nouveau thème" })).toBeNull();
    first.unmount();

    auth.isAdmin = true;
    await renderPage();
    await fireEvent.click(screen.getByLabelText("Rapprochements"));
    expect(screen.getByRole("button", { name: "Nouveau thème" })).toBeTruthy();
    auth.isAdmin = false;
  });


  it("cherche par un POST, montre les résultats et ouvre un dossier", async () => {
    mockApi.post("/api/search", FOUND);
    await renderPage();
    await searchFor("lilas");

    expect(await screen.findByText(/2 dossier\(s\) trouvé\(s\)/)).toBeTruthy();
    expect(mockApi.calls[0]!.body).toEqual({ query: "lilas", limit: 20 });
    await fireEvent.click(screen.getByText("Camille"));
    expect(screen.getByRole("link", { name: "Ouvrir le dossier" }).getAttribute("href")).toBe("/dossiers/a");
    await fireEvent.click(screen.getByText("Pourquoi ?"));
    expect(screen.getByText("La même valeur apparaît.")).toBeTruthy();
    expect(screen.getByText("Entité : Analyse Titre de séjour · Adresse")).toBeTruthy();
  });

  it("ne laisse pas une réponse en retard écraser la recherche suivante", async () => {
    let release: (value: unknown) => void = () => {};
    mockApi.post("/api/search", ({ body }: { body: any }) =>
      body.query === "lente" ? new Promise((resolve) => (release = resolve)) : FOUND,
    );
    await renderPage();
    await searchFor("lente");
    await searchFor("rapide");
    await screen.findByText(/2 dossier\(s\) trouvé\(s\)/);

    release({ dossiers: [], total: 0, items: [] });
    await new Promise((resolve) => setTimeout(resolve));

    expect(screen.getByText(/2 dossier\(s\) trouvé\(s\)/)).toBeTruthy();
  });

  it("annonce le nombre de dossiers non accessibles que donne le serveur", async () => {
    const hidden = [{ theme_name: "Sécurité routière", count: 3, dossier_ids: ["a"] }];
    mockApi.post("/api/search", { ...FOUND, hidden });
    await renderPage();
    await searchFor("lilas");

    expect(await screen.findByText("3 dossiers non accessibles · Sécurité routière")).toBeTruthy();
  });

  it("présente un rapprochement d'écritures différentes comme incertain", async () => {
    mockApi.post("/api/search", { ...FOUND, items: [{ ...sharedAddress, uncertain: true }] });
    await renderPage();
    await searchFor("lilas");
    await fireEvent.click(await screen.findByText("Camille"));
    await fireEvent.click(screen.getByText("Pourquoi ?"));

    expect(screen.getByText("Des écritures proches apparaissent.")).toBeTruthy();
    expect(screen.getByText(/Rapprochement incertain/)).toBeTruthy();
  });

  it("dit quand la recherche échoue", async () => {
    mockApi.fail("POST", "/api/search", 503, "La recherche a échoué, réessayez.");
    await renderPage();
    await searchFor("lilas");

    expect(await screen.findByText("La recherche a échoué, réessayez.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeTruthy();
  });

  it("reprend la sélection de l'adresse et montre les dossiers liés", async () => {
    mockApi.post("/api/search/links", LINKS);
    await renderPage("/recherche?dossiers=a");

    expect(await screen.findByText("Dossiers liés à votre sélection (1)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retirer Camille" })).toBeTruthy();
    expect(mockApi.calls[0]!.body).toEqual({ dossier_ids: ["a"], include_related: true });
  });

  it("part des dossiers cochés et les met dans l'adresse", async () => {
    mockApi.post("/api/search", FOUND).post("/api/search/links", LINKS);
    const { router } = await renderPage();
    await searchFor("lilas");
    await fireEvent.click(await screen.findByLabelText("Sélectionner Camille"));
    await fireEvent.click(screen.getByRole("button", { name: "Voir les liens (1)" }));

    await waitFor(() => expect(router.currentRoute.value.query.dossiers).toBe("a"));
    expect(await screen.findByRole("button", { name: "Retirer Camille" })).toBeTruthy();
  });

  it("retire un dossier devenu inaccessible sans bloquer les autres", async () => {
    mockApi.post("/api/search/links", ({ body }: { body: any }) => {
      if (body.dossier_ids.includes("gone")) {
        throw new ApiError(404, "Dossier introuvable", { code: "dossiers_not_found", dossier_ids: ["gone"] });
      }
      return LINKS;
    });
    await renderPage("/recherche?dossiers=a,gone");

    expect(await screen.findByText(/1 dossier\(s\) retiré\(s\)/)).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Retirer Camille" })).toBeTruthy();
  });

  it("n'annonce des données fictives que pour les rapprochements", async () => {
    await renderPage();
    expect(screen.queryByText("données fictives")).toBeNull();

    await fireEvent.click(screen.getByLabelText("Rapprochements"));
    expect(screen.getByText("données fictives")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: /Adresse partagée/ }));
    await fireEvent.click(screen.getByRole("button", { name: /12 rue des Lilas/ }));
    expect(screen.queryByRole("button", { name: "Explorer ces dossiers" })).toBeNull();
  });
});
