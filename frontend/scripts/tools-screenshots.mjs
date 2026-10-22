// Les écrans simulés sont masqués par défaut : lancer le serveur de dev avec VITE_TOOLS_PREVIEW=true pour les capturer
//   VITE_TOOLS_PREVIEW=true pnpm dev
// Usage « vérifier que tout est masqué » (serveur de dev lancé SANS la variable) : node scripts/tools-screenshots.mjs --verifier-masque
// Captures de la page « Mes outils » et du sélecteur de tools d'un agent (docs/tools-mcp-plan.md, phase 1).
// Les écrans s'appuient sur des données simulées côté interface ; l'API est simulée ici (interception de /api/**).
// Le serveur de dev doit tourner (pnpm dev).
// Usage : node scripts/tools-screenshots.mjs [url]   (défaut : http://localhost:5173)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.argv.slice(2).find((arg) => !arg.startsWith("--")) ?? "http://localhost:5173";
const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/frontend/tools");
mkdirSync(outDir, { recursive: true });

const iso = (days) => new Date(Date.now() + days * 86_400_000).toISOString();
const ANALYSE_ID = "an-subv";
const profile = { user_id: "u1", email: "alex.martin@example.org", first_name: "Alex", last_name: "Martin", roles: [], is_admin: false, groups: ["/service-culture"] };

const analyse = {
  id: ANALYSE_ID,
  name: "Instruction subventions",
  description: "Instruction des demandes de subvention des associations.",
  created_at: iso(-90),
  version: "v1",
  classification: { prompt: "", prompt_versions: [], labels: [], labels_versions: [] },
  extraction: { prompt: "", prompt_versions: [], entities: [], entities_versions: [] },
  statuses: [],
  statuses_versions: [],
  due_settings: { default_due_days: null, thresholds: { far_color: "#18753c", steps: [], overdue_color: "#8a0000" } },
  due_settings_versions: [],
  custom_fields: [],
  custom_fields_versions: [],
  agents: [
    {
      id: "ag-1",
      name: "Contrôle de conformité juridique",
      prompt: "Vérifie que la demande respecte les textes applicables et cite les articles pertinents.",
      prompt_versions: [],
      tools: ["calculatrice", "recherche_web", "base_connaissances", "srv-legifrance-rechercher_texte", "srv-supprime-ancien_tool"],
      tools_versions: [{ id: "tv-1", created_at: iso(-4), content: ["calculatrice", "recherche_web"] }],
      output: true,
      output_versions: [],
      model: null,
      model_versions: [],
    },
  ],
};

const DOSSIER = {
  id: "dos-1",
  name: "Subvention association Les Mouettes n°102",
  analyse_id: ANALYSE_ID,
  analyse_version: "v1",
  created_at: iso(-3),
  status: "terminé",
  started_at: iso(-3),
  ended_at: iso(-3),
  execution_steps: [],
  documents: [],
  summary_status: "terminé",
  summary_error: null,
  summary: null,
  suggestion_status: "terminé",
  suggested_analyses: [],
  workflow_status: null,
  visibility: "analyse",
  closed_at: null,
  due_at: null,
  due: null,
  closed_before_due: null,
};
const MESSAGES = [
  { id: "m1", role: "user", content: "Le RIB de l'association est-il bien dans le dossier ?", created_at: iso(-0.01), sources: [], feedback: null },
  { id: "m2", role: "assistant", content: "Je ne trouve pas de RIB dans les pièces fournies : seuls les statuts et le dossier de demande sont présents.", created_at: iso(-0.01), sources: [], feedback: null },
];

// --- Registre des tools : réponses de l'API (mêmes formes que backend/app/schemas/tool.py) ---
const internal = (id, name, description, side_effect = false, config = null) => ({ id, name, description, kind: "internal", server_id: null, side_effect, enabled: true, config });
const INTERNAL_TOOLS = [
  internal("lecture_document", "Lecture de document", "Lit le contenu d'un document du dossier, page par page."),
  internal("recherche_web", "Recherche web", "Cherche une information sur le web."),
  internal("base_connaissances", "Base de connaissances", "Interroge la base de connaissances de la plateforme.", false, "collections"),
  internal("appel_agent", "Appel à un autre agent", "Délègue une sous-tâche à un autre agent de l'analyse."),
  internal("calculatrice", "Calculatrice", "Effectue des calculs exacts (montants, taux, totaux)."),
  internal("verification_coherence", "Vérification de cohérence", "Compare des informations entre documents et signale les écarts."),
  internal("recherche_dossier", "Recherche dans le dossier", "Cherche des passages dans les documents du dossier."),
  internal("calcul_dates", "Calcul de dates", "Délais, échéances et durées entre deux dates."),
  internal("notes_internes", "Notes internes", "Ajoute une note interne au dossier.", true),
  internal("propositions_analyse", "Propositions de modification de l'analyse", "Propose de modifier un élément de l'analyse, à valider par une personne.", true),
];
const mcp = (server, name, description, side_effect = false, enabled = true) => ({ id: `${server}-${name}`, name, description, kind: "mcp", server_id: server, side_effect, enabled, config: null });
const server = (id, name, url, auth_mode, visibility, owner_name, owned_by_me, days, tools, audience = null) => ({ id, name, url, auth_mode, audience: auth_mode === "token_exchange" ? (audience ?? `mcp-${id.replace("srv-", "")}`) : null, visibility, owner_name, owned_by_me, synced_at: iso(-days), tools });
let SERVERS = [
  server("srv-legifrance", "Légifrance", "https://mcp.legifrance.example.gouv.fr/mcp", "token_exchange", "all", "Camille Roux", false, 2, [
    mcp("srv-legifrance", "rechercher_texte", "Recherche un texte de loi ou de règlement par mots-clés."),
    mcp("srv-legifrance", "lire_article", "Renvoie le contenu en vigueur d'un article."),
    mcp("srv-legifrance", "historique_article", "Liste les versions successives d'un article.", false, false),
  ]),
  server("srv-jurisprudence", "Jurisprudence interne", "https://jurisprudence.example.interieur.gouv.fr/mcp", "token_exchange", "private", "Alex Martin", true, 0, [
    mcp("srv-jurisprudence", "rechercher_decision", "Recherche une décision par juridiction, date ou thème."),
    mcp("srv-jurisprudence", "decisions_similaires", "Trouve les décisions proches d'un résumé de dossier."),
  ]),
  server("srv-annuaire", "Annuaire des services", "https://annuaire.example.service-public.gouv.fr/mcp", "none", "groups", "Alex Martin", true, 6, [
    mcp("srv-annuaire", "trouver_service", "Trouve le service compétent pour une démarche."),
    mcp("srv-annuaire", "envoyer_courriel", "Envoie un courriel à un service.", true),
  ]),
  server("srv-cadastre", "Cadastre", "https://cadastre.example.gouv.fr/mcp", "none", "all", "Camille Roux", false, 9, [
    mcp("srv-cadastre", "trouver_parcelle", "Renvoie la parcelle cadastrale d'une adresse."),
    mcp("srv-cadastre", "surface_parcelle", "Renvoie la surface d'une parcelle."),
  ]),
  server("srv-sirene", "Répertoire des entreprises", "https://sirene.example.insee.fr/mcp", "token_exchange", "all", "Sam Leroy", false, 4, [
    mcp("srv-sirene", "rechercher_entreprise", "Recherche une entreprise par nom ou SIREN."),
    mcp("srv-sirene", "etablissements", "Liste les établissements d'une entreprise."),
  ]),
  server("srv-associations", "Registre des associations", "https://rna.example.associations.gouv.fr/mcp", "token_exchange", "groups", "Alex Martin", true, 1, [
    mcp("srv-associations", "rechercher_association", "Recherche une association par nom ou numéro RNA."),
    mcp("srv-associations", "statuts_association", "Renvoie les statuts déposés d'une association."),
  ]),
  server("srv-subventions", "Historique des subventions", "https://subventions.example.finances.gouv.fr/mcp", "token_exchange", "private", "Alex Martin", true, 3, [
    mcp("srv-subventions", "subventions_percues", "Liste les subventions déjà perçues par un bénéficiaire."),
  ]),
];
const DISCOVERED = [
  { name: "rechercher", description: "Recherche dans la base du serveur.", side_effect: false },
  { name: "consulter_fiche", description: "Renvoie le détail d'une fiche.", side_effect: false },
  { name: "creer_fiche", description: "Crée une nouvelle fiche.", side_effect: true },
];

const toolTestRoute = (route, path) => {
  const match = path.match(/^\/api\/tools\/(.+)\/test$/);
  if (!match || route.request().method() !== "POST") return false;
  const body = route.request().postDataJSON();
  const toolName = match[1].replace(/^srv-[a-z]+-/, "");
  const model = body.model || "mistral-medium";
  const call = { name: toolName, arguments: { requete: body.prompt.slice(0, 60) } };
  const send = (payload) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ truncated: false, model, call, ...payload }) });
  if (body.prompt.includes("999")) {
    send({ ok: false, code: "outil_en_erreur", output: "Article introuvable : 999", duration_ms: 214 });
  } else {
    send({ ok: true, code: null, output: JSON.stringify({ resultats: [{ titre: "Article L1111-1", extrait: "…" }, { titre: "Article L1111-2", extrait: "…" }], total: 2 }), duration_ms: 618 });
  }
  return true;
};

const agentToolsRoute = (route, path) => {
  const json = (body) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  const agent = analyse.agents[0];
  if (path === `/api/analyses/${ANALYSE_ID}/agents/ag-1/tools` && route.request().method() === "PUT") {
    agent.tools_versions = [{ id: `tv-${Date.now()}`, created_at: new Date().toISOString(), content: agent.tools }, ...agent.tools_versions];
    agent.tools = route.request().postDataJSON().tools;
    json(agent);
    return true;
  }
  return false;
};

const handler = (route) => {
  const path = new URL(route.request().url()).pathname;
  const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (path === "/api/tools/internal") return json(INTERNAL_TOOLS);
  if (path === "/api/tool-servers" && route.request().method() === "GET") return json({ items: SERVERS, total: SERVERS.length, page: 1, page_size: 100, pages: 1 });
  if (path === "/api/tool-servers/discover") {
    const body = route.request().postDataJSON();
    if (!body.url.startsWith("https://")) return json({ detail: "L'adresse doit utiliser https." }, 422);
    return json({ tools: DISCOVERED });
  }
  if (path === "/api/tool-servers" && route.request().method() === "POST") {
    const body = route.request().postDataJSON();
    const added = server("srv-nouveau", body.name, body.url, body.auth_mode, body.visibility, "Alex Martin", true, 0, DISCOVERED.map((t) => mcp("srv-nouveau", t.name, t.description, t.side_effect, body.tool_names.includes(t.name))), body.audience);
    SERVERS = [added, ...SERVERS];
    return json(added, 201);
  }
  if (agentToolsRoute(route, path) || toolTestRoute(route, path)) return;
  if (path === "/api/auth/me") return json(profile);
  if (path === "/api/cgu/acceptance") return json({ accepted: true, cgu: null });
  if (path === "/api/cgu") return json({}, 404);
  if (path === `/api/analyses/${ANALYSE_ID}`) return json(analyse);
  if (path === "/api/dossiers/dos-1") return json(DOSSIER);
  if (/^\/api\/dossiers\/dos-1\/conversations$/.test(path)) return json({ items: [{ id: "conv-1", dossier_id: "dos-1", created_by: "u1", title: null, model: null, created_at: iso(-1), updated_at: iso(0) }], total: 1, page: 1, page_size: 100 });
  if (/^\/api\/dossiers\/dos-1\/conversations\/conv-1\/messages/.test(path)) return json({ items: MESSAGES, has_more: false });
  if (/^\/api\/dossiers\/dos-1\/conversations\/conv-1$/.test(path)) return json({ id: "conv-1", dossier_id: "dos-1", created_by: "u1", title: null, model: null, created_at: iso(-1), updated_at: iso(0), messages: MESSAGES });
  if (path.startsWith("/api/dossiers/dos-1/")) { console.log("non simulé :", path); return json([]); }
  if (path === "/api/models") return json({ models: [{ id: "mistral-medium" }] });
  if (path.startsWith("/api/reports") || path.startsWith("/api/me/tasks")) return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 20 });
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "fr-FR", timezoneId: "Europe/Paris" });
const page = await context.newPage();
await page.route("**/api/**", handler);

// --- Vérification du masquage : sans VITE_TOOLS_PREVIEW, aucun écran simulé n'apparaît ---
if (process.argv.includes("--verifier-masque")) {
  const failures = [];
  const expect = (ok, message) => { console.log(`${ok ? "✓" : "✗"} ${message}`); if (!ok) failures.push(message); };

  await page.goto(`${baseUrl}/outils`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  expect(await page.getByRole("heading", { name: "Mes outils" }).count() === 1, "« Mes outils » (page réelle) reste visible");
  expect(await page.locator(".server-card__tool").getByRole("button", { name: "Tester" }).count() > 0, "« Mes outils » : « Tester » sur les tools MCP (réel)");
  expect(await page.locator(".internal-tool").getByRole("button", { name: "Tester" }).count() === 0, "« Mes outils » : pas de « Tester » sur les outils internes");

  await page.goto(`${baseUrl}/analyses/${ANALYSE_ID}/agents`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  expect(await page.getByRole("button", { name: "Choisir les outils" }).count() > 0, "Agents : le sélecteur d'outils (réel) est visible");
  // (la case « Base de connaissances » de l'éditeur d'origine existe : on vise le titre du bloc simulé)
  expect(await page.getByRole("heading", { name: "Base de connaissances" }).count() === 0, "Agents : pas de collections simulées");

  await page.goto(`${baseUrl}/dossiers/dos-1`, { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  expect(await page.getByRole("button", { name: "Outils de la conversation" }).count() === 0, "Chat : pas de menu des outils");

  await browser.close();
  process.exit(failures.length ? 1 : 0);
}

const settle = (ms = 500) => page.waitForTimeout(ms);
const shot = async (file, locator) => {
  await settle(600);
  const path = resolve(outDir, file);
  await (locator ?? page).screenshot(locator ? { path } : { path, fullPage: true });
  console.log(`✓ tools/${file}`);
};

// 1. Page « Mes outils »
await page.goto(`${baseUrl}/outils`, { waitUntil: "networkidle" });
await shot("page-outils.png");

// 1 bis. Recherche dans « Mes outils »
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("association");
await shot("page-outils-recherche.png");
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("");

// 1 ter. Testeur d'un outil (entrée / sortie)
const testButton = (tool) => page.locator(".server-card__tool", { hasText: tool }).getByRole("button", { name: "Tester" });
const testShot = async (file) => {
  await page.screenshot({ path: resolve(outDir, file) });
  console.log(`✓ tools/${file}`);
};
await page.setViewportSize({ width: 1280, height: 950 });
await page.evaluate(() => window.scrollTo(0, 0));
await testButton("rechercher_texte").click();
await settle(1200);
await testShot("test-outil-avant.png");
await page.getByRole("button", { name: "Lancer le test" }).click();
await settle(1500);
await testShot("test-outil-succes.png");
await page.keyboard.press("Escape");
await settle(500);

await testButton("lire_article").click();
await settle(1200);
await page.getByLabel("Demande au modèle").fill("Lis l'article 999.");
await page.getByRole("button", { name: "Lancer le test" }).click();
await settle(1500);
await testShot("test-outil-erreur.png");
await page.keyboard.press("Escape");
await settle(500);

await testButton("envoyer_courriel").click();
await settle(1200);
await testShot("test-outil-effet-de-bord.png");
await page.keyboard.press("Escape");
await settle(500);
await page.setViewportSize({ width: 1280, height: 800 });

// 2. Ajout d'un serveur MCP : formulaire (jeton statique grisé)
await page.setViewportSize({ width: 1280, height: 1500 });
await page.getByRole("button", { name: "Ajouter un serveur MCP" }).first().click();
await page.getByPlaceholder("Légifrance").fill("Registre des associations");
await page.getByPlaceholder("https://exemple.gouv.fr/mcp").fill("https://rna.example.associations.gouv.fr/mcp");
await page.getByPlaceholder("mcp-legifrance").fill("mcp-registre-associations");
await shot("ajout-serveur.png", page.locator(".fr-modal--opened .fr-modal__body"));

// 2 bis. Une erreur de l'API (adresse en http) s'affiche dans le formulaire
await page.getByPlaceholder("https://exemple.gouv.fr/mcp").fill("http://rna.example.associations.gouv.fr/mcp");
await page.getByRole("button", { name: "Importer les tools" }).click();
await settle(600);
await shot("ajout-serveur-erreur.png", page.locator(".fr-modal--opened .fr-modal__body"));
await page.getByPlaceholder("https://exemple.gouv.fr/mcp").fill("https://rna.example.associations.gouv.fr/mcp");

// 3. Ajout d'un serveur MCP : choix des tools importés
await page.getByRole("button", { name: "Importer les tools" }).click();
await shot("import-tools.png", page.locator(".fr-modal--opened .fr-modal__body"));
await page.keyboard.press("Escape");
await page.setViewportSize({ width: 1280, height: 800 });

// 4. Sélecteur de tools dans l'onglet Agents de l'analyse
await page.goto(`${baseUrl}/analyses/${ANALYSE_ID}/agents`, { waitUntil: "networkidle" });
await shot("selecteur-agent.png");

// 4 ter. Un outil devenu indisponible est signalé, la personne le retire et enregistre
const editor = page.locator(".agent-tools-editor");
await shot("agent-outil-indisponible.png", editor);
await page.getByRole("button", { name: /Retirer l'outil indisponible/ }).click();
await page.getByRole("button", { name: "Enregistrer", exact: true }).last().click();
await settle(600);
await page.getByText("Historique des versions").last().click();
await settle(400);
await shot("agent-outils-enregistres.png", editor);

// 4 bis. Collections de la base de connaissances (analyse)
await page.screenshot({ path: resolve(outDir, "collections-analyse.png"), fullPage: true });
console.log("✓ tools/collections-analyse.png");
await page.setViewportSize({ width: 1280, height: 1250 });
await page.getByRole("button", { name: "Choisir les collections" }).click();
await settle(1200);
await page.screenshot({ path: resolve(outDir, "collections-modale.png") });
console.log("✓ tools/collections-modale.png");
await page.getByPlaceholder("Rechercher une collection…").fill("jurisprudence");
await settle(400);
await page.screenshot({ path: resolve(outDir, "collections-recherche.png") });
console.log("✓ tools/collections-recherche.png");
await page.keyboard.press("Escape");
await settle(500);
await page.setViewportSize({ width: 1280, height: 800 });

// 5. Modale de choix des tools de l'agent
await page.setViewportSize({ width: 1280, height: 1100 });
await page.getByRole("button", { name: "Choisir les outils" }).click();
await settle(1500);
await page.screenshot({ path: resolve(outDir, "selecteur-modale.png") });
console.log("✓ tools/selecteur-modale.png");
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("rechercher_texte");
await settle(300);
await page.locator(".tool-picker-row", { hasText: "rechercher_texte" }).getByRole("button", { name: "Tester" }).click();
await settle(1200);
await page.screenshot({ path: resolve(outDir, "test-outil-agent.png") });
console.log("✓ tools/test-outil-agent.png");
await page.locator(".fr-modal--opened").last().getByRole("button", { name: "Fermer", exact: true }).last().click();
await settle(500);
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("article");
await settle(400);
await page.screenshot({ path: resolve(outDir, "selecteur-modale-recherche.png") });
console.log("✓ tools/selecteur-modale-recherche.png");

// 6. Chat du dossier : outils disponibles, puis confirmation avant un tool qui modifie des données
await page.setViewportSize({ width: 1280, height: 900 });
await page.goto(`${baseUrl}/dossiers/dos-1`, { waitUntil: "networkidle" });
await settle(800);
await page.screenshot({ path: resolve(outDir, "chat-outils.png") });
console.log("✓ tools/chat-outils.png");
// Menu des outils dans la zone d'envoi, comme ChatGPT
await page.getByRole("button", { name: "Outils de la conversation" }).click();
await settle(400);
await page.screenshot({ path: resolve(outDir, "chat-menu-outils.png") });
console.log("✓ tools/chat-menu-outils.png");

await page.locator(".chat-tools-menu__list").evaluate((el) => (el.scrollTop = el.scrollHeight));
await settle(300);
await page.screenshot({ path: resolve(outDir, "chat-menu-mcp.png") });
console.log("✓ tools/chat-menu-mcp.png");
await page.locator(".chat-tools-menu__list").evaluate((el) => (el.scrollTop = 0));

await page.getByLabel("Recherche web").uncheck({ force: true });
await page.getByLabel("Appel à un autre agent").uncheck({ force: true });
await page.getByLabel("Vérification de cohérence").uncheck({ force: true });
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("recherche");
await settle(300);
await page.screenshot({ path: resolve(outDir, "chat-menu-recherche.png") });
console.log("✓ tools/chat-menu-recherche.png");

await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("");
await page.keyboard.press("Escape");
await settle(300);
await page.screenshot({ path: resolve(outDir, "chat-outils-desactives.png") });
console.log("✓ tools/chat-outils-desactives.png");

// Confirmation avant un tool qui modifie des données
await page.evaluate(() => window.__toolsMock.askConfirmation());
await settle(500);
await page.screenshot({ path: resolve(outDir, "chat-confirmation.png") });
console.log("✓ tools/chat-confirmation.png");

await browser.close();
