import { fireEvent, render, screen, waitFor } from "@testing-library/vue";
import VueDsfr from "@gouvminint/vue-dsfr";
import { describe, expect, it, vi } from "vitest";
import { reactive, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

import CriteriaEditor from "@/components/crossSearch/CriteriaEditor.vue";
import CrossSearchPage from "@/pages/CrossSearchPage.vue";
import { mockApi } from "@/test/mockApi";
import { SHARED_KINDS, type CrossSearchResult, type Resemblance, type RuleCriterion } from "@/types/crossSearch";
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

/** Un petit graphe : trois dossiers, une adresse et un identifiant partagés. */
const graphResult = (anchorIds: string[] = []): CrossSearchResult => ({
  query: "",
  anchorIds,
  dossiers: ["d1", "d2", "d3"].map((id) => ({
    id,
    reference: id,
    name: id,
    analyseName: null,
    themeName: null,
    excerpts: [],
  })),
  items: [
    { id: "a-lilas", kind: "value", label: "12 rue des Lilas", dossierIds: ["d1", "d2"], occurrences: [] },
    { id: "i-permis", kind: "identifier", label: "PERMIS-000123", dossierIds: ["d2", "d3"], occurrences: [] },
  ],
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

const ENTITIES = [
  { id: "e-titulaire", name: "Titulaire du permis", definition: "", type: "texte", analyse_name: "Permis" },
  { id: "e-demandeur", name: "Nom du demandeur", definition: "", type: "texte", analyse_name: "Titre de séjour" },
  { id: "e-gerant", name: "Gérant", definition: "", type: "texte", analyse_name: "Licence" },
];

const THEME = {
  id: "t1",
  name: "Personne revenant",
  description: "",
  scope: "all",
  certainty: "probable",
  active: true,
  criteria: [{ id: "c1", origin: "analysis", name: "Personne", entity_ids: ["e-titulaire"], refused_ids: [] }],
  computed_at: "2026-11-28T08:00:00Z",
  group_count: 1,
  versions: [],
  missing_entity_ids: [],
};

const GROUP = {
  key: "g1",
  label: "Camille Exemple",
  reason: "En commun : personne.",
  certainty: "probable",
  dossiers: [dossier("a", "Camille"), dossier("b", "Sacha")],
  occurrences: [proof("a"), proof("b")],
  dismissed: false,
};

const groupsRoute = /\/api\/resemblances\/themes\/t1\/groups\?/;

function mockResemblanceApi(enabled = true) {
  mockApi
    .get("/api/resemblances/themes", { enabled, items: [THEME] })
    .get(groupsRoute, { items: enabled ? [GROUP] : [], total: enabled ? 1 : 0, page: 1, page_size: 20 });
}

async function openResemblances() {
  const view = await renderPage();
  await fireEvent.click(screen.getByLabelText("Rapprochements"));
  return view;
}

describe("rapprochements", () => {
  it("montre un groupe, ses dossiers, et permet de les explorer", async () => {
    mockResemblanceApi();
    mockApi.post("/api/search/links", LINKS);
    const { router } = await openResemblances();

    await fireEvent.click(await screen.findByRole("button", { name: /Camille Exemple\s*2 dossiers/ }));
    expect(screen.getByText("En commun : personne.")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Explorer ces dossiers" }));

    await waitFor(() => expect(router.currentRoute.value.query.dossiers).toBe("a,b"));
  });

  it("écarte un rapprochement faux", async () => {
    mockResemblanceApi();
    mockApi.post("/api/resemblances/themes/t1/groups/g1/dismiss", undefined);
    await openResemblances();
    await fireEvent.click(await screen.findByRole("button", { name: /Camille Exemple\s*2 dossiers/ }));
    await fireEvent.click(screen.getByRole("button", { name: "Écarter : ce rapprochement est faux" }));

    await waitFor(() => expect(mockApi.calls.some((c) => c.path.endsWith("/g1/dismiss"))).toBe(true));
  });

  it("dit quand le calcul n'est pas activé", async () => {
    mockResemblanceApi(false);
    await openResemblances();

    expect(await screen.findByText(/Le calcul des rapprochements n'est pas activé/)).toBeTruthy();
  });

  it("réserve la définition des thèmes aux administrateurs", async () => {
    mockResemblanceApi();
    await openResemblances();
    await screen.findByText(/Dernier calcul/);

    expect(screen.queryByRole("button", { name: "Nouveau thème" })).toBeNull();
  });
});

describe("critères d'un thème", () => {
  const entities = ENTITIES.map((e) => ({ ...e, type: "texte" as const, analyseName: e.analyse_name }));
  const suggestions = "/api/resemblances/entities/suggestions";
  // Réactif, comme le brouillon du thème dans la fenêtre : le composant modifie le critère en place.
  const renderEditor = (modelValue: RuleCriterion[]) => {
    const view = render(CriteriaEditor, {
      props: {
        entities,
        modelValue: reactive(modelValue),
        "onUpdate:modelValue": (value: unknown) => view.rerender({ modelValue: value as RuleCriterion[] }),
      },
    });
  };
  const criterion = (): RuleCriterion => ({ id: "c", origin: "analysis", name: "Personne", entityIds: ["e-titulaire"] });
  const accepted = "Titre de séjour › Nom du demandeur";
  const refused = "Licence › Gérant";

  it("n'ajoute une entité proposée qu'après accord, et permet de revenir sur un refus", async () => {
    mockApi.post(suggestions, { available: true, items: [ENTITIES[1], ENTITIES[2]] });
    renderEditor([criterion()]);
    expect(await screen.findByRole("button", { name: `Accepter ${accepted}` })).toBeTruthy();
    expect(screen.queryByRole("button", { name: `Retirer ${accepted}` })).toBeNull();

    await fireEvent.click(screen.getByRole("button", { name: `Accepter ${accepted}` }));
    expect(screen.getByRole("button", { name: `Retirer ${accepted}` })).toBeTruthy();

    await fireEvent.click(await screen.findByRole("button", { name: `Refuser ${refused}` }));
    expect(screen.queryByRole("button", { name: `Accepter ${refused}` })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: `Reproposer ${refused}` }));
    expect(screen.getByRole("button", { name: `Accepter ${refused}` })).toBeTruthy();
  });

  it("dit quand les propositions sont indisponibles", async () => {
    mockApi.post(suggestions, { available: false, items: [] });
    renderEditor([criterion()]);

    expect(await screen.findByText(/Propositions indisponibles ici/)).toBeTruthy();
  });

  it("retrouve une entité par sa description, sans jamais en créer", async () => {
    mockApi.post(suggestions, ({ body }: { body: any }) => ({
      available: true,
      items: body.text === "Nom du gérant" ? [ENTITIES[2]] : [],
    }));
    renderEditor([]);
    const search = screen.getByLabelText("Ou décrire l'information recherchée");
    await fireEvent.update(search, "Groupe sanguin");
    expect(await screen.findByText(/Aucune analyse n'extrait cette information/)).toBeTruthy();

    await fireEvent.update(search, "Nom du gérant");
    await fireEvent.click(await screen.findByRole("button", { name: `Utiliser ${refused}` }));
    expect(screen.getByRole("button", { name: "Retirer le critère Gérant" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Entité personnalisée" })).toBeNull();
  });
});

describe("layoutClusters", () => {
  it("fait un amas par groupe, sans que les amas se touchent", () => {
    const groups = ["g1", "g2", "g3"].map((id) => ({ id, dossierIds: ["a", "b"] }) as Resemblance);
    const { nodes, clusters } = layoutClusters(groups);

    expect(clusters.map((c) => c.groupId)).toEqual(["g1", "g2", "g3"]);
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
});
