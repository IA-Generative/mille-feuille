// Captures de la page « Recherche » (docs/frontend/recherche-entre-dossiers). L'API est simulée ici (interception de
// /api/**) avec des personnes et des dossiers fictifs.
// Le serveur de dev doit tourner (pnpm dev).
// Usage : node scripts/search-screenshots.mjs [url]   (défaut : http://localhost:5173)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const outDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/frontend/recherche-entre-dossiers");
mkdirSync(outDir, { recursive: true });

const profile = { user_id: "u1", email: "alex.martin@example.org", first_name: "Alex", last_name: "Martin", roles: [], is_admin: false, groups: [] };

const excerpt = (document_name, page, before, found, after) => ({
  document_id: `doc-${document_name}`, document_name, page, field: null,
  segments: [{ text: before, highlighted: false }, { text: found, highlighted: true }, { text: after, highlighted: false }],
});
const dossier = (id, number, name, analyse_name, theme_name, excerpts) => ({
  id, reference: `DOS-2026-${String(number).padStart(4, "0")}`, name, analyse_name, theme_name, excerpts,
});

const DOSSIERS = [
  dossier("d1", 12, "Titre de séjour — Camille Exemple", "Titre de séjour", "Séjour des étrangers", [
    excerpt("justificatif_domicile.pdf", 1, "Camille Exemple réside au 12 rue des ", "Lilas", " depuis le 3 mars."),
  ]),
  dossier("d2", 31, "Regroupement familial — Sacha Exemple", "Regroupement familial", "Séjour des étrangers", [
    excerpt("demande.pdf", 1, "Le demandeur déclare habiter au 12 rue des ", "Lilas", "."),
  ]),
  dossier("d5", 54, "Attestation d'hébergement — Dominique Modèle", "Titre de séjour", "Séjour des étrangers", [
    excerpt("attestation.pdf", 1, "Dominique Modèle, hébergé au 12 rue des ", "Lilas", "."),
  ]),
  dossier("d6", 60, "Licence de transport — Transports Fictifs", "Licence de transport", "Sécurité routière", [
    excerpt("kbis.pdf", 1, "Siège : 4 allée des ", "Lilas", ", gérant Dominique Modèle."),
  ]),
];

const proof = (dossier_id, document_name, text, origin) => ({ dossier_id, document_id: `doc-${document_name}`, document_name, page: 1, text, origin });
const ITEMS = [
  {
    id: "value:adresse", kind: "value", label: "12 rue des Lilas", dossier_ids: ["d1", "d2", "d5"],
    occurrences: [
      proof("d1", "justificatif_domicile.pdf", "12 rue des Lilas", "Analyse Titre de séjour · Adresse"),
      proof("d2", "demande.pdf", "12 rue des Lilas", "Analyse Regroupement familial · Domicile déclaré"),
      proof("d5", "attestation.pdf", "12 Rue des Lilas", "Analyse Titre de séjour · Adresse"),
    ],
  },
  {
    id: "value:gerant", kind: "value", label: "Dominique Modèle", dossier_ids: ["d5", "d6"],
    occurrences: [
      proof("d5", "attestation.pdf", "Dominique Modèle", "Analyse Titre de séjour · Hébergeant"),
      proof("d6", "kbis.pdf", "Dominique Modèle", "Analyse Licence de transport · Gérant"),
    ],
  },
  {
    id: "identifier:permis", kind: "identifier", label: "PERMIS-000123", dossier_ids: ["d1", "d6"],
    occurrences: [
      proof("d1", "permis.pdf", "PERMIS-000123", "Analyse Titre de séjour · Numéro de permis"),
      proof("d6", "conducteurs.pdf", "PERMIS-000123", "Analyse Licence de transport · Permis du conducteur"),
    ],
  },
  {
    id: "document:attestation", kind: "document", label: "attestation_hebergement.pdf", dossier_ids: ["d2", "d5"],
    occurrences: ["d2", "d5"].map((dossier_id) => ({ dossier_id, document_id: "f", document_name: "attestation_hebergement.pdf", page: null, text: "", origin: null })),
  },
];
const HIDDEN = [{ theme_name: "Sécurité routière", count: 3, dossier_ids: ["d1", "d6"] }];

const THEME = {
  id: "t1", name: "Personne dans plusieurs thèmes", description: "Une même personne suivie par des services différents.",
  scope: "across", certainty: "probable", active: true, computed_at: "2026-11-28T08:00:00Z", group_count: 1, versions: [], missing_entity_ids: [],
  criteria: [{ id: "c1", origin: "analysis", name: "Personne", entity_ids: ["e1", "e2"], refused_ids: [] }],
};
const GROUP = {
  key: "g1", label: "Dominique Modèle", reason: "En commun : personne.", certainty: "probable", dismissed: false,
  dossiers: [DOSSIERS[2], DOSSIERS[3]].map((d) => ({ ...d, excerpts: [] })),
  occurrences: ITEMS[1].occurrences,
};

const handler = async (route) => {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  if (path === "/api/auth/me") return json(profile);
  if (path === "/api/cgu/acceptance") return json({ accepted: true, cgu: null });
  if (path === "/api/cgu") return json({}, 404);
  if (path === "/api/resemblances/themes") return json({ enabled: true, items: [THEME] });
  if (path === "/api/resemblances/themes/t1/groups") return json({ items: [GROUP], total: 1, page: 1, page_size: 20 });
  if (path === "/api/search") return json({ dossiers: DOSSIERS, total: DOSSIERS.length, items: ITEMS, hidden: HIDDEN });
  if (path === "/api/search/links") {
    const anchors = request.postDataJSON().dossier_ids;
    const items = ITEMS.filter((item) => item.dossier_ids.some((id) => anchors.includes(id)));
    const linked = new Set(items.flatMap((item) => item.dossier_ids));
    const shown = [...anchors, ...[...linked].filter((id) => !anchors.includes(id))];
    return json({ anchor_ids: anchors, dossiers: shown.map((id) => ({ ...DOSSIERS.find((d) => d.id === id), excerpts: [] })), items, hidden: HIDDEN });
  }
  if (path === "/api/me/tasks" || path === "/api/reports") return json([]);
  return json({ items: [], total: 0, page: 1, page_size: 20 });
};

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH, args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "fr-FR", timezoneId: "Europe/Paris" });
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
await page.route("**/api/**", handler);

const shot = async (name) => {
  // Le graphe se place après le rendu.
  await page.waitForTimeout(1500);
  await page.screenshot({ path: resolve(outDir, name), fullPage: true });
};

await page.goto(`${baseUrl}/recherche`);
await page.getByRole("searchbox", { name: "Mots-clés" }).fill("lilas");
await page.getByRole("button", { name: "Rechercher", exact: true }).click();
await page.getByText("dossier(s) trouvé(s)").waitFor();
await shot("01-resultats.png");

await page.locator(".result-list__item", { hasText: "Titre de séjour — Camille Exemple" }).click();
await shot("02-detail-dossier.png");
await page.getByRole("button", { name: /12 rue des Lilas.*Pourquoi/ }).click();
await shot("03-pourquoi-ce-lien.png");

await page.goto(`${baseUrl}/recherche?dossiers=d1`);
await page.getByText("Dossiers liés à votre sélection").waitFor();
await shot("04-a-partir-de-dossiers.png");

await page.getByText("Rapprochements", { exact: true }).click();
await page.getByRole("button", { name: /Dominique Modèle\s*2 dossiers/ }).click();
await shot("05-rapprochements.png");

await browser.close();
if (errors.length) console.error("Erreurs de page :", errors);
console.log(`Captures écrites dans ${outDir}`);
