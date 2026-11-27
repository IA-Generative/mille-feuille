import { fireEvent, render, screen } from "@testing-library/vue";
import VueDsfr from "@gouvminint/vue-dsfr";
import { describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import { mockLinksFrom, mockSearch } from "@/composables/useCrossSearch";
import CrossSearchPage from "@/pages/CrossSearchPage.vue";
import { SHARED_KINDS } from "@/types/crossSearch";
import CriteriaEditor from "@/components/crossSearch/CriteriaEditor.vue";
import { allOfKind } from "@/composables/mockEntityCatalog";
import { mockResemblances, useResemblances } from "@/composables/useResemblances";
import { layoutClusters } from "@/utils/clusterLayout";
import { buildLinkGraph, highlightOf, restrictToKinds } from "@/utils/linkGraph";

const auth = vi.hoisted(() => ({ isAdmin: false }));
vi.mock("@/composables/useAuth", () => ({ useAuth: () => ({ isAdmin: ref(auth.isAdmin) }) }));
// sigma.js a besoin de WebGL, absent de jsdom.
vi.mock("@/components/crossSearch/ClusterGraph.vue", () => ({ default: { template: "<div />" } }));
vi.mock("@/components/crossSearch/LinkGraph.vue", () => ({ default: { template: "<div />" } }));

const renderPage = () =>
  render(CrossSearchPage, { global: { plugins: [VueDsfr], stubs: { RouterLink: true, VIcon: true } } });

async function searchFor(query: string) {
  await fireEvent.update(screen.getByRole("searchbox"), query);
  await fireEvent.click(screen.getByRole("button", { name: /rechercher/i }));
}

describe("mockSearch", () => {
  it("ne relie que les points communs à au moins deux résultats", () => {
    const result = mockSearch("lilas");

    expect(result.dossiers.map((d) => d.id).sort()).toEqual(["d1", "d2", "d5"]);
    expect(result.items.every((item) => item.dossierIds.length > 1)).toBe(true);
  });

  it("ne signale aucun dossier non accessible sans résultat accessible", () => {
    expect(mockSearch("introuvable").hidden).toEqual([]);
    expect(mockSearch("permis-000123").hidden.map((h) => h.themeName)).toEqual(["Sécurité routière"]);
  });
});

describe("buildLinkGraph", () => {
  it("retire les types décochés sans retirer les dossiers", () => {
    const result = mockSearch("exemple");
    const graph = buildLinkGraph(result, []);

    expect(graph.nodes.filter((n) => n.type === "item")).toEqual([]);
    expect(graph.nodes.filter((n) => n.type === "dossier")).toHaveLength(result.dossiers.length);
    const ids = new Set(graph.nodes.map((n) => n.id));
    expect(graph.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  });
});

describe("highlightOf", () => {
  const graph = buildLinkGraph(mockSearch("exemple"), SHARED_KINDS.map((k) => k.value));

  it("met en avant le trait choisi seul, ou les chemins entre deux dossiers", () => {
    const link = highlightOf(graph, { type: "link", dossierId: "d1", targetId: "a-lilas" })!;
    expect([...link.nodes].sort()).toEqual(["a-lilas", "d1"]);

    const pair = highlightOf(graph, { type: "pair", dossierIds: ["d3", "d4"] })!;
    expect([...pair.nodes].sort()).toEqual(["d3", "d4", "i-permis", "p-camille"]);
    expect(pair.edges.size).toBe(4);
  });
});

describe("mockLinksFrom", () => {
  it("ne montre que ce qui touche la sélection", () => {
    const result = mockLinksFrom(["d2"], true);

    expect(result.dossiers.map((d) => d.id)).toEqual(["d2", "d1", "d5"]);
    expect(result.items.every((item) => item.dossierIds.includes("d2"))).toBe(true);
    expect(mockLinksFrom(["d2"], false).items).toEqual([]);
  });

  it("garde les dossiers choisis quand un filtre retire les autres", () => {
    const result = restrictToKinds(mockLinksFrom(["d2"], true), ["document"]);

    expect(result.dossiers.map((d) => d.id)).toEqual(["d2", "d5"]);
    expect(restrictToKinds(mockLinksFrom(["d2"], true), []).dossiers.map((d) => d.id)).toEqual(["d2"]);
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
    const first = renderPage();
    await fireEvent.click(screen.getByLabelText("Rapprochements"));
    expect(screen.queryByRole("button", { name: "Nouveau thème" })).toBeNull();
    first.unmount();

    auth.isAdmin = true;
    renderPage();
    await fireEvent.click(screen.getByLabelText("Rapprochements"));
    expect(screen.getByRole("button", { name: "Nouveau thème" })).toBeTruthy();
    auth.isAdmin = false;
  });


  it("montre un thème à la fois, détaille un groupe et ouvre ses dossiers", async () => {
    renderPage();
    await fireEvent.click(screen.getByLabelText("Rapprochements"));

    expect(screen.getByRole("heading", { name: "Dossiers possiblement en double" })).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: /Adresse partagée/ }));
    expect(screen.queryByRole("heading", { name: "Dossiers possiblement en double" })).toBeNull();
    expect(screen.getByText(/1 groupe réunissant 3 dossiers/)).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: /12 rue des Lilas/ }));
    expect(screen.getByText("À vérifier")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Explorer ces dossiers" }));
    expect(screen.getByRole("button", { name: "Retirer Titre de séjour — Camille Exemple" })).toBeTruthy();
  });

  it("part des dossiers cochés et montre ceux qui leur sont liés", async () => {
    renderPage();
    await searchFor("lilas");
    await fireEvent.click(screen.getByLabelText("Sélectionner Titre de séjour — Camille Exemple"));
    await fireEvent.click(screen.getByLabelText("Sélectionner Regroupement familial — Sacha Exemple"));
    await fireEvent.click(screen.getByRole("button", { name: "Voir les liens (2)" }));

    expect(screen.getByText("Entre vos dossiers")).toBeTruthy();
    expect(screen.getByText("par 12 rue des Lilas")).toBeTruthy();
    expect(screen.getByText(/Dossiers liés à votre sélection/)).toBeTruthy();
  });

  it("ajoute un dossier à la sélection depuis le champ, puis le retire", async () => {
    renderPage();
    await fireEvent.click(screen.getByLabelText("À partir de dossiers"));
    await fireEvent.update(screen.getByLabelText("Ajouter un dossier"), "DOS-2026-0048");
    await fireEvent.click(screen.getByRole("button", { name: /Échange de permis/ }));

    expect(screen.getByRole("button", { name: "Retirer Échange de permis — Camille Exemple" })).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "Retirer Échange de permis — Camille Exemple" }));
    expect(screen.getByText(/Choisissez un ou plusieurs dossiers/)).toBeTruthy();
  });


  it("annonce que la fonctionnalité arrive et que les données sont fictives", () => {
    renderPage();

    expect(screen.getByText("Fonctionnalité bientôt disponible")).toBeTruthy();
    expect(screen.getByText("données fictives")).toBeTruthy();
  });

  it("liste les dossiers trouvés et annonce les liens non accessibles", async () => {
    renderPage();
    await searchFor("lilas");

    expect(screen.getByText("Titre de séjour — Camille Exemple")).toBeTruthy();
    expect(screen.getByText("2 dossiers non accessibles · Séjour des étrangers")).toBeTruthy();
  });

  it("détaille le dossier choisi", async () => {
    renderPage();
    await searchFor("lilas");
    await fireEvent.click(screen.getByText("Titre de séjour — Camille Exemple"));

    expect(screen.getByText("Points communs (1)")).toBeTruthy();
    expect(screen.getByText("Dossiers liés (2)")).toBeTruthy();
  });

  it("explique pourquoi un dossier est lié, preuve à l'appui", async () => {
    renderPage();
    await searchFor("lilas");
    await fireEvent.click(screen.getByText("Titre de séjour — Camille Exemple"));
    await fireEvent.click(screen.getByText("Pourquoi ?"));

    expect(screen.getByText("Pourquoi ce lien ?")).toBeTruthy();
    expect(screen.getByText("La même adresse apparaît.")).toBeTruthy();
    expect(screen.getByText("justificatif_domicile.pdf, page 1")).toBeTruthy();
    expect(screen.getByText("Entité : Analyse Titre de séjour · Adresse")).toBeTruthy();
  });

  it("compare deux dossiers avec la preuve de chaque côté", async () => {
    renderPage();
    await searchFor("lilas");
    await fireEvent.click(screen.getByText("Titre de séjour — Camille Exemple"));
    await fireEvent.click(screen.getByText("Regroupement familial — Sacha Exemple"));

    expect(screen.getByText("Ce qui les relie (1)")).toBeTruthy();
    expect(screen.getByText("demande.pdf, page 1")).toBeTruthy();
  });

  it("dit quand rien d'accessible ne correspond", async () => {
    renderPage();
    await searchFor("introuvable");

    expect(screen.getByText(/Aucun dossier accessible/)).toBeTruthy();
    expect(screen.queryByText(/ne vous sont pas ouverts/)).toBeNull();
  });
});
