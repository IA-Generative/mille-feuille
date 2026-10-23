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
      tools: ["calculatrice", "calcul_dates", "recherche_web", "srv-legifrance-rechercher_texte", "srv-supprime-ancien_tool"],
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
  documents: [{ id: "doc-statuts", name: "Statuts de l'association.pdf", size: 120000, s3_key: "k", mimetype: "application/pdf", label: null, text_extraction_status: "terminé", text_extraction_error: null, file_hash: null, created_at: iso(-3), source: null, summary_status: "terminé", summary_error: null, summary: null }],
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
  { id: "m3", role: "user", content: "Préviens le service des subventions et l'association.", created_at: iso(-0.005), sources: [], feedback: null },
  {
    id: "m4", role: "assistant", content: "Je peux envoyer ces deux courriels. J'ai besoin de votre accord.", created_at: iso(-0.004), sources: [], feedback: null,
    tool_calls: [
      { id: "tc-1", message_id: "m4", position: 0, tool_name: "envoyer_courriel", server_name: "Annuaire des services", arguments: { destinataire: "service-subventions@culture.example.gouv.fr", objet: "Pièce manquante : RIB de l'association" }, side_effect: true, status: "pending", decided_at: null },
      { id: "tc-2", message_id: "m4", position: 1, tool_name: "envoyer_courriel", server_name: "Annuaire des services", arguments: { destinataire: "contact@association.example.org", objet: "Votre dossier : un RIB est à fournir" }, side_effect: true, status: "pending", decided_at: null },
    ],
  },
];
// Une question à choix de l'assistant, ajoutée à la conversation par la dernière étape des captures.
const QUESTION_CALL = {
  id: "tc-q", message_id: "m6", position: 0, tool_id: "ask_user", tool_name: "ask_user", server_name: "", side_effect: false, status: "pending", decided_at: null,
  arguments: {
    questions: [
      { question: "À quel service faut-il écrire ?", header: "Service", multi_select: false, options: [{ label: "Subventions", description: "Le guichet qui instruit la demande" }, { label: "Finances", description: "Le bureau qui gère les versements" }] },
      { question: "Quelles pièces joindre au courriel ?", header: "Pièces", multi_select: true, options: [{ label: "RIB", description: "Celui de l'association" }, { label: "Statuts", description: "La dernière version" }, { label: "Procès-verbal", description: "De la dernière assemblée" }] },
    ],
  },
};
const answerRoute = (route, path) => {
  if (path !== "/api/dossiers/dos-1/conversations/conv-1/tool-calls/tc-q/answer") return false;
  QUESTION_CALL.status = "executed";
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(QUESTION_CALL) });
  return true;
};
// La décision d'un lot : tout le lot ensemble (comme POST .../tool-calls/decisions du backend).
const decisionRoute = (route, path) => {
  if (path !== "/api/dossiers/dos-1/conversations/conv-1/tool-calls/decisions") return false;
  const calls = MESSAGES.find((m) => m.id === "m4").tool_calls;
  for (const { id, allow } of route.request().postDataJSON().decisions) calls.find((c) => c.id === id).status = allow ? "approved" : "refused";
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(calls) });
  return true;
};

// --- Registre des tools : réponses de l'API (mêmes formes que backend/app/schemas/tool.py) ---
const internal = (id, name, description, side_effect = false, config = null) => ({ id, name, description, kind: "internal", server_id: null, side_effect, enabled: true, config });
const INTERNAL_TOOLS = [
  internal("calculatrice", "Calculatrice", "Effectue des calculs exacts : montants, taux, totaux, pourcentages."),
  internal("calcul_dates", "Calcul de dates", "Jour de la semaine, ajout d'une durée, écart entre deux dates, bornes d'un mois ou d'un trimestre, date du jour."),
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

let chatExcluded = [];
const chatTool = (id, name, description, kind, server_name, side_effect = false) => ({ id, name, description, kind, server_name, side_effect });
const CHAT_TOOLS = [
  chatTool("calculatrice", "Calculatrice", "Effectue des calculs exacts : montants, taux, totaux, pourcentages.", "internal", null),
  chatTool("calcul_dates", "Calcul de dates", "Jour de la semaine, ajout d'une durée, écart entre deux dates, bornes d'un mois ou d'un trimestre, date du jour.", "internal", null),
  chatTool("srv-legifrance-rechercher_texte", "rechercher_texte", "Recherche un texte de loi ou de règlement par mots-clés.", "mcp", "Légifrance"),
  chatTool("srv-annuaire-trouver_service", "trouver_service", "Trouve le service compétent pour une démarche.", "mcp", "Annuaire des services"),
  chatTool("srv-annuaire-envoyer_courriel", "envoyer_courriel", "Envoie un courriel à un service.", "mcp", "Annuaire des services", true),
];
const conversationToolsRoute = (route, path) => {
  if (path !== "/api/dossiers/dos-1/conversations/conv-1/tools") return false;
  if (route.request().method() === "PUT") {
    const known = new Set(CHAT_TOOLS.map((t) => t.id));
    chatExcluded = [...new Set(route.request().postDataJSON().excluded)].filter((id) => known.has(id));
  }
  route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ tools: CHAT_TOOLS, excluded: chatExcluded, unavailable: ["srv-supprime-ancien_tool"] }) });
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

// --- Base de connaissances : sources, collections d'un fournisseur, collections de l'analyse (mêmes formes que l'API) ---
const pageImage = (lines) => `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="210" height="297" viewBox="0 0 210 297"><rect width="210" height="297" fill="#fff"/><rect x="0.5" y="0.5" width="209" height="296" fill="none" stroke="#ddd"/>${lines.map((y) => `<rect x="25" y="${y}" width="${y % 3 ? 160 : 120}" height="5" rx="2" fill="#c9c9c9"/>`).join("")}</svg>`)}`;
const PAGE_PREVIEW = pageImage([40, 55, 70, 85, 100, 115, 130, 145, 160, 175, 190, 205, 220, 235]);
const col = (id, name, description, document_count, extra = {}) => ({ id, name, description, document_count, url: null, preview_url: null, ...extra });
const KB_SOURCES = [
  { id: "kb-refs", name: "Textes de référence", url: "https://base-de-connaissances.example.gouv.fr", auth_mode: "token_exchange", audience: "kb-refs", visibility: "all", owner_name: "Camille Roux", owned_by_me: false, created_at: iso(-30) },
  { id: "kb-service-public", name: "Sites officiels", url: "https://kb-sites.example.gouv.fr", auth_mode: "none", audience: null, visibility: "private", owner_name: "Alex Martin", owned_by_me: true, created_at: iso(-4) },
];
const KB_COLLECTIONS = {
  "kb-refs": [
    col("ceseda", "CESEDA : textes et commentaires", "Code de l'entrée et du séjour des étrangers et du droit d'asile.", 1240, { url: "https://base-de-connaissances.example.gouv.fr/c/ceseda", preview_url: pageImage([40, 60, 80, 100, 120]) }),
    col("ce", "Jurisprudence du Conseil d'État", "Décisions du Conseil d'État depuis 1990.", 8410, { preview_url: pageImage([40, 70, 100, 130]) }),
    col("ta", "Jurisprudence des tribunaux administratifs", "Décisions des tribunaux administratifs.", 12030),
    col("circulaires", "Circulaires et instructions ministérielles", "Circulaires publiées au Bulletin officiel.", 960),
    col("subv-guide", "Guide de l'instruction des subventions", "Procédures et pièces à exiger pour une subvention.", 85, { url: "https://base-de-connaissances.example.gouv.fr/c/subv-guide", preview_url: PAGE_PREVIEW }),
    col("courriers", "Modèles de courriers", "Courriers types de l'administration.", 140),
    col("crpa", "Code des relations entre le public et l'administration", "Textes et commentaires du CRPA.", 420),
    col("cgct", "Code général des collectivités territoriales", "Textes et commentaires du CGCT.", 2100),
    col("secu-routiere", "Code de la sécurité routière", "Textes, barèmes et commentaires.", 760),
    col("doctrine", "Doctrine interne", "Notes de doctrine des services.", 230),
    col("reponses", "Réponses ministérielles", "Réponses aux questions parlementaires.", 5100),
  ],
  "kb-service-public": [
    col("service-public", "Fiches pratiques Service-Public", "Fiches pratiques à destination des usagers.", 3500, { url: "https://www.service-public.example.fr" }),
    col("associations", "Associations : démarches", "Création, subventions et obligations des associations.", 310),
  ],
};
const sourceName = (id) => KB_SOURCES.find((s) => s.id === id).name;
const collectionOf = (sourceId, collectionId) => KB_COLLECTIONS[sourceId]?.find((c) => c.id === collectionId);
let ANALYSE_KB = [{ source_id: "kb-refs", collection_id: "subv-guide", name: "Guide de l'instruction des subventions" }, { source_id: "kb-refs", collection_id: "crpa", name: "Code des relations entre le public et l'administration" }, { source_id: "kb-refs", collection_id: "circulaires", name: "Circulaires et instructions ministérielles" }, { source_id: "kb-service-public", collection_id: "associations", name: "Associations : démarches" }];
let ANALYSE_KB_VERSIONS = [
  { id: "kv-2", created_at: iso(-6), content: ANALYSE_KB.slice(0, 2) },
  { id: "kv-1", created_at: iso(-20), content: ANALYSE_KB.slice(0, 1) },
];
// La collection « circulaires » a disparu chez le fournisseur, et la personne n'a plus droit à « crpa ».
const analyseKbOut = () => ({
  collections: ANALYSE_KB.map((item) => {
    const found = collectionOf(item.source_id, item.collection_id);
    const status = item.collection_id === "crpa" ? "forbidden" : found && item.collection_id !== "circulaires" ? "available" : "not_found";
    return { ...item, name: found?.name ?? item.name, source_name: sourceName(item.source_id), status };
  }),
  versions: ANALYSE_KB_VERSIONS,
});
const knowledgeRoute = (route, path) => {
  const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  const method = route.request().method();
  if (path === "/api/knowledge-sources" && method === "GET") return json({ items: KB_SOURCES, total: KB_SOURCES.length, page: 1, page_size: 100, pages: 1 }), true;
  if (path === "/api/knowledge-sources" && method === "POST") {
    const body = route.request().postDataJSON();
    if (body.url.includes("refuse")) return json({ detail: "Le fournisseur a refusé l'authentification." }, 502), true;
    KB_SOURCES.unshift({ id: "kb-nouveau", name: body.name, url: body.url, auth_mode: body.auth_mode, audience: body.audience, visibility: body.visibility, owner_name: "Alex Martin", owned_by_me: true, created_at: new Date().toISOString() });
    KB_COLLECTIONS["kb-nouveau"] = [];
    return json(KB_SOURCES[0], 201), true;
  }
  const check = path.match(/^\/api\/knowledge-sources\/([^/]+)\/check$/);
  if (check) return route.fulfill({ status: 204 }), true;
  const list = path.match(/^\/api\/knowledge-sources\/([^/]+)\/collections$/);
  if (list) {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") ?? "").toLowerCase();
    const page = Number(url.searchParams.get("page") ?? 1);
    const size = Number(url.searchParams.get("page_size") ?? 20);
    const all = (KB_COLLECTIONS[list[1]] ?? []).filter((c) => `${c.name} ${c.description}`.toLowerCase().includes(q));
    return json({ items: all.slice((page - 1) * size, page * size), total: all.length, page, page_size: size, pages: Math.max(1, Math.ceil(all.length / size)) }), true;
  }
  if (path === `/api/analyses/${ANALYSE_ID}/knowledge-collections`) {
    if (method === "PUT") {
      const refs = route.request().postDataJSON().collections;
      ANALYSE_KB_VERSIONS = [{ id: `kv-${Date.now()}`, created_at: new Date().toISOString(), content: ANALYSE_KB }, ...ANALYSE_KB_VERSIONS];
      ANALYSE_KB = refs.map((r) => ({ ...r, name: collectionOf(r.source_id, r.collection_id)?.name ?? ANALYSE_KB.find((o) => o.collection_id === r.collection_id)?.name ?? r.collection_id }));
    }
    return json(analyseKbOut()), true;
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
  if (agentToolsRoute(route, path) || toolTestRoute(route, path) || conversationToolsRoute(route, path) || knowledgeRoute(route, path) || decisionRoute(route, path) || answerRoute(route, path)) return;
  if (path === "/api/auth/me") return json(profile);
  if (path === "/api/cgu/acceptance") return json({ accepted: true, cgu: null });
  if (path === "/api/cgu") return json({}, 404);
  if (path === `/api/analyses/${ANALYSE_ID}`) return json(analyse);
  if (path === "/api/dossiers/dos-1") return json(DOSSIER);
  if (/^\/api\/dossiers\/dos-1\/conversations$/.test(path)) return json({ items: [{ id: "conv-1", dossier_id: "dos-1", created_by: "u1", title: null, model: null, created_at: iso(-1), updated_at: iso(0) }], total: 1, page: 1, page_size: 100 });
  if (/^\/api\/dossiers\/dos-1\/conversations\/conv-1\/messages/.test(path)) return json({ items: MESSAGES, has_more: false });
  if (/^\/api\/dossiers\/dos-1\/conversations\/conv-1$/.test(path)) return json({ id: "conv-1", dossier_id: "dos-1", created_by: "u1", title: null, model: null, created_at: iso(-1), updated_at: iso(0), messages: MESSAGES });
  if (/^\/api\/dossiers\/dos-1\/documents\/doc-statuts\/pages\/[^/]+\/screenshot$/.test(path)) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: decodeURIComponent(PAGE_PREVIEW.split(",")[1]) });
  if (path.startsWith("/api/dossiers/dos-1/")) { console.log("non simulé :", path); return json([]); }
  if (path === "/api/models") return json({ models: [{ id: "mistral-medium" }] });
  if (path.startsWith("/api/reports") || path.startsWith("/api/me/tasks")) return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 20 });
};

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "fr-FR", timezoneId: "Europe/Paris" });
const page = await context.newPage();
await page.route("**/api/**", handler);

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

// 1 quater. Ajout d'une source de connaissances : la connexion est vérifiée avant l'enregistrement
await page.getByRole("button", { name: "Ajouter une source de connaissances" }).click();
await settle(600);
await page.getByLabel("Nom").first().fill("Doctrine interne");
await page.getByLabel(/Adresse de l'API/).fill("https://refuse.example.gouv.fr");
await page.getByLabel(/Audience Keycloak/).fill("kb-doctrine");
await page.getByRole("button", { name: "Vérifier et ajouter" }).click();
await settle(700);
await page.screenshot({ path: resolve(outDir, "ajout-source-erreur.png") });
console.log("✓ tools/ajout-source-erreur.png");
await page.getByLabel(/Adresse de l'API/).fill("https://doctrine.example.gouv.fr");
await settle(300);
await page.screenshot({ path: resolve(outDir, "ajout-source.png") });
console.log("✓ tools/ajout-source.png");
await page.getByRole("button", { name: "Annuler" }).last().click();
await settle(500);

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
for (let i = 0; i < 2; i++) await page.getByRole("button", { name: /Retirer l'outil indisponible/ }).first().click();
await page.getByRole("button", { name: "Enregistrer", exact: true }).last().click();
await settle(600);
await page.getByText("Historique des versions").last().click();
await settle(400);
await shot("agent-outils-enregistres.png", editor);

// 4 bis. Collections de la base de connaissances (analyse) : l'état est celui de la personne qui regarde
await settle(400);
await shot("collections-analyse.png", page.locator(".knowledge-field"));
await page.setViewportSize({ width: 1280, height: 1250 });
await page.getByRole("button", { name: "Choisir les collections" }).click();
await settle(1200);
await page.screenshot({ path: resolve(outDir, "collections-modale.png") });
console.log("✓ tools/collections-modale.png");
await page.getByRole("tab", { name: "Sites officiels" }).click();
await settle(500);
await page.screenshot({ path: resolve(outDir, "collections-modale-source.png") });
console.log("✓ tools/collections-modale-source.png");
await page.getByRole("tab", { name: "Textes de référence" }).click();
await page.getByPlaceholder("Rechercher une collection…").fill("jurisprudence");
await settle(900);
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

await page.getByLabel("Calculatrice").uncheck({ force: true });
await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("recherche");
await settle(300);
await page.screenshot({ path: resolve(outDir, "chat-menu-recherche.png") });
console.log("✓ tools/chat-menu-recherche.png");

await page.getByPlaceholder("Rechercher un outil, un serveur…").fill("");
await page.keyboard.press("Escape");
await settle(300);
await page.screenshot({ path: resolve(outDir, "chat-outils-desactives.png") });
console.log("✓ tools/chat-outils-desactives.png");

// Demande d'autorisation avant des tools qui modifient des données : une carte, un onglet par appel, une validation
const card = page.locator(".tool-call-card");
// La zone d'envoi colle au bas de l'écran : on centre la carte et on capture la fenêtre, pas l'élément.
const cardShot = async (file) => {
  await card.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await settle(600);
  await page.screenshot({ path: resolve(outDir, file) });
  console.log(`✓ tools/${file}`);
};
await cardShot("chat-confirmation.png");
await card.getByRole("button", { name: "Autoriser", exact: true }).click();
await cardShot("chat-confirmation-onglets.png");
await card.getByPlaceholder("Refuser et dire quoi faire à la place…").fill("Écris plutôt à la cheffe de bureau.");
await card.getByPlaceholder("Refuser et dire quoi faire à la place…").press("Enter");
await cardShot("chat-confirmation-prete.png");
await card.getByRole("button", { name: "Valider" }).click();
await settle(800);
await cardShot("chat-confirmation-decidee.png");

// Question à choix de l'assistant : onglets, choix unique et multiple, « Autre », une validation
MESSAGES.push(
  { id: "m5", role: "user", content: "Écris au service concerné.", created_at: iso(-0.002), sources: [], feedback: null },
  { id: "m6", role: "assistant", content: "J'ai besoin de deux précisions avant d'écrire.", created_at: iso(-0.001), sources: [], feedback: null, tool_calls: [QUESTION_CALL] },
);
await page.reload({ waitUntil: "networkidle" });
await settle(800);
const questionCard = page.locator(".tool-question");
const questionShot = async (file) => {
  await questionCard.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await settle(600);
  await page.screenshot({ path: resolve(outDir, file) });
  console.log(`✓ tools/${file}`);
};
await questionShot("chat-question.png");
await questionCard.getByText("Finances").click();
await settle(300);
await questionCard.getByLabel("RIB").check({ force: true });
await questionCard.getByLabel("Statuts").check({ force: true });
await questionCard.getByPlaceholder("Autre…").fill("et le procès-verbal de mars");
await questionShot("chat-question-multiple.png");
await questionCard.getByRole("button", { name: "Valider" }).click();
await settle(800);
await questionShot("chat-question-repondue.png");

// Sources de la réponse : pages du dossier et base de connaissances sur une même suite numérotée, en carrousel
const DOSSIER_SOURCE = { id: "src-1", number: 1, dossier_document_id: "doc-statuts", execution_step_id: null, excerpt: "Article 3 : le RIB de l'association est joint à toute demande de subvention.", pages: [{ id: "pg-2", page_number: 2 }], bounding_boxes: [{ id: "bb-1", document_page_id: "pg-2", x_min: 0.12, y_min: 0.22, x_max: 0.86, y_max: 0.3 }] };
const EXTERNAL_SOURCES = [
  { number: 2, source_id: "p-8f2c", kind: "document", title: "Guide de l'instruction des subventions 2026.pdf", url: "https://base-de-connaissances.example.gouv.fr/v1/documents/d-120?page=14", preview_url: PAGE_PREVIEW, page: 14, boxes: [{ page: 14, x_min: 0.1, y_min: 0.34, x_max: 0.9, y_max: 0.46 }], passage: "Toute demande de subvention comporte les statuts de l'association, un RIB, le budget prévisionnel de l'exercice et le dernier rapport d'activité.", score: 0.91, collection_name: "Guide de l'instruction des subventions", source_name: "Textes de référence" },
  { number: 3, source_id: "w-31", kind: "web", title: "Service-Public.fr — Subvention aux associations", url: "https://www.service-public.example.fr/associations/subvention", preview_url: null, page: null, boxes: [], passage: "Les pièces à joindre varient selon le montant demandé et la collectivité qui instruit la demande.", score: 0.77, collection_name: "Fiches pratiques Service-Public", source_name: "Sites officiels" },
];
MESSAGES.push(
  { id: "m7", role: "user", content: "Quelles pièces faut-il exiger pour une subvention ?", created_at: iso(-0.0005), sources: [], feedback: null },
  {
    id: "m8", role: "assistant", created_at: iso(-0.0004), feedback: null,
    content: "Le RIB de l'association doit être joint à la demande [1]. Une demande comporte aussi les statuts et le budget prévisionnel [2], et les pièces varient selon le montant demandé [3].",
    sources: [DOSSIER_SOURCE],
    external_sources: EXTERNAL_SOURCES,
  },
);
await page.reload({ waitUntil: "networkidle" });
await settle(1000);
const carousel = page.locator(".source-carousel").last();
const carouselShot = async (file) => {
  await carousel.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await settle(700);
  await page.screenshot({ path: resolve(outDir, file) });
  console.log(`✓ tools/${file}`);
};
await carouselShot("chat-sources-carrousel.png");
// Un clic sur un numéro du texte place le carrousel sur la bonne carte
await page.getByRole("link", { name: "[2]" }).last().click();
await settle(900);
await carouselShot("chat-sources-numero.png");
await carousel.getByRole("button", { name: "Source suivante" }).click();
await settle(900);
await carouselShot("chat-sources-carrousel-suite.png");

// Une seule source : pas de carrousel
MESSAGES.push(
  { id: "m9", role: "user", content: "Qui est le président de l'association ?", created_at: iso(-0.0003), sources: [], feedback: null },
  { id: "m10", role: "assistant", created_at: iso(-0.0002), feedback: null, content: "D'après les statuts, le président est élu pour trois ans [1].", sources: [{ ...DOSSIER_SOURCE, id: "src-2", excerpt: "Le président est élu par l'assemblée générale pour une durée de trois ans." }], external_sources: [] },
);
await page.reload({ waitUntil: "networkidle" });
await settle(1000);
await page.locator(".source-carousel").last().evaluate((el) => el.scrollIntoView({ block: "center" }));
await settle(700);
await page.screenshot({ path: resolve(outDir, "chat-source-unique.png") });
console.log("✓ tools/chat-source-unique.png");

// Les sources des réponses plus anciennes sont repliées ; la dernière réponse montre les siennes
await page.locator(".source-carousel").first().evaluate((el) => el.scrollIntoView({ block: "center" }));
await settle(700);
await page.screenshot({ path: resolve(outDir, "chat-sources-repliees.png") });
console.log("✓ tools/chat-sources-repliees.png");

await browser.close();
