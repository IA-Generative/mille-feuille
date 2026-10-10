// Prend les captures d'écran de la documentation du tableau de bord (#174), des statuts de dossier (#170), de l'historique du dossier (#171), de l'échéance (#172),
// du tableau de suivi (#173, #186), de l'accès par groupe (#177) et du détail des résultats d'un dossier, sous
// docs/frontend/<fonctionnalité>/.
//
// Les écrans s'appuient sur des données simulées côté interface ; l'API est
// simulée ici (interception des appels /api/**) pour ne dépendre ni du
// backend ni de Keycloak. Le serveur de dev doit tourner (pnpm dev).
//
// Usage : node scripts/doc-screenshots.mjs [url] [fonctionnalité…]   (défaut : http://localhost:5173, toutes)
//         ex. node scripts/doc-screenshots.mjs http://localhost:5173 due
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const baseUrl = process.argv[2] ?? "http://localhost:5173";
const docsRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/frontend");

const ANALYSE_ID = "an-subv";
const iso = (days) => new Date(Date.now() + days * 86_400_000).toISOString();

const profiles = {
  admin: { user_id: "u1", email: "alex.martin@example.org", first_name: "Alex", last_name: "Martin", roles: ["admin"], is_admin: true, groups: ["/service-culture", "/service-sport"] },
  user: { user_id: "u1", email: "alex.martin@example.org", first_name: "Alex", last_name: "Martin", roles: [], is_admin: false, groups: ["/service-culture", "/service-sport"] },
};

const STATUS = (id, name, color, position, is_initial = false, is_final = false) => ({
  id,
  name,
  color,
  position,
  is_initial,
  is_final,
});

const STATUSES = [
  STATUS("st-1", "À instruire", "#6a6af4", 0, true),
  STATUS("st-2", "En instruction", "#0063cb", 1),
  STATUS("st-3", "Pièces manquantes", "#b34000", 2),
  STATUS("st-4", "À valider", "#8585f6", 3),
  STATUS("st-5", "Clos", "#18753c", 4, false, true),
];

const dossier = (n, name, extra = {}) => ({
  id: `dos-${n}`,
  name,
  analyse_id: ANALYSE_ID,
  analyse_version: "v1",
  created_at: iso(-n),
  status: "terminé",
  started_at: iso(-n),
  ended_at: iso(-n),
  execution_steps: [],
  documents: [],
  summary_status: "terminé",
  summary_error: null,
  summary: null,
  suggestion_status: "terminé",
  suggested_analyses: [],
  workflow_status: STATUSES[n % 3],
  visibility: "analyse",
  closed_at: null,
  due_at: null,
  due: null,
  closed_before_due: null,
  ...extra,
});

// Échéance (#172) : le serveur calcule le niveau selon les seuils de l'analyse ; l'API simulée en fait autant.
const DEFAULT_DUE = {
  default_due_days: 30,
  thresholds: { far_color: "#18753c", steps: [{ days: 30, color: "#b34000" }, { days: 7, color: "#ce0500" }], overdue_color: "#8a0000" },
};
const dayKey = (days) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
const daysUntil = (dueAt) => Math.round((Date.parse(`${dueAt}T00:00:00Z`) - Date.parse(`${dayKey(0)}T00:00:00Z`)) / 86_400_000);
function dueOf(d, thresholds) {
  if (!d.due_at) return null;
  const days_left = daysUntil(d.due_at);
  if (d.closed_at) return { level: "closed", days_left, color: null };
  if (days_left < 0) return { level: "overdue", days_left, color: thresholds.overdue_color };
  const step = [...thresholds.steps].sort((a, b) => a.days - b.days).find((s) => days_left <= s.days);
  return { level: step ? "soon" : "ok", days_left, color: step ? step.color : thresholds.far_color };
}

const dossiers = [
  dossier(3, "Subvention association Les Mouettes n°102", {
    due_at: dayKey(5),
    visibility: "restricted",
    documents: [
      {
        id: "doc-1",
        name: "dossier-de-demande.pdf",
        size: 482113,
        s3_key: "dossiers/dos-3/doc-1",
        mimetype: "application/pdf",
        label: null,
        text_extraction_status: "terminé",
        text_extraction_error: null,
        file_hash: null,
        summary_status: "terminé",
        summary_error: null,
        summary: null,
      },
    ],
  }),
  dossier(1, "Convention de partenariat culturelle n°100", { due_at: dayKey(-4) }),
  dossier(9, "Aide au projet sportif jeunesse n°108", { workflow_status: STATUSES[2], due_at: dayKey(40) }),
];

// Détail des résultats d'un dossier : un dossier à part, pour ne pas changer les captures des autres fonctionnalités.
const RESULTS_FILES = [
  { id: "doc-r1", name: "demande-de-titre-de-sejour.pdf", pages: 3 },
  { id: "doc-r2", name: "justificatifs-de-domicile.pdf", pages: 5 },
];
const RESULTS_DOSSIER = dossier(20, "Recours titre de séjour n°215", {
  summary_status: "en_attente",
  documents: RESULTS_FILES.map((f) => ({
    id: f.id,
    name: f.name,
    size: 482113,
    s3_key: `dossiers/dos-20/${f.id}`,
    mimetype: "application/pdf",
    label: null,
    text_extraction_status: "terminé",
    text_extraction_error: null,
    file_hash: null,
    summary_status: "terminé",
    summary_error: null,
    summary: null,
  })),
  execution_steps: [
    { id: "st-cl", kind: "classification", label: "Classification", status: "terminé", started_at: iso(-1), ended_at: iso(-1), output: "8/8 page(s) classifiée(s)" },
    { id: "st-ex", kind: "extraction", label: "Entités", status: "terminé", started_at: iso(-1), ended_at: iso(-1), output: "24 entité(s) extraite(s) sur 8 page(s)" },
  ],
});
const resultPage = (f, n) => ({ id: `pg-${f.id}-${n}`, page_number: n });
const resultBox = (f, n) => ({ id: `bb-${f.id}-${n}`, document_page_id: `pg-${f.id}-${n}`, x_min: 0.08, y_min: 0.17, x_max: 0.62, y_max: 0.24 });
// Page « scannée » factice : un en-tête, des lignes de texte et un bloc encadré par la zone du résultat.
const resultPageSvg = (title) => `<svg xmlns="http://www.w3.org/2000/svg" width="620" height="877" viewBox="0 0 620 877"><rect width="620" height="877" fill="#fff"/><rect x="40" y="40" width="180" height="14" rx="3" fill="#161616"/><text x="40" y="110" font-family="Marianne, Arial, sans-serif" font-size="22" font-weight="bold" fill="#161616">${title}</text>${Array.from({ length: 22 }, (_, i) => `<rect x="40" y="${200 + i * 28}" width="${480 - ((i * 53) % 160)}" height="9" rx="3" fill="#cecece"/>`).join("")}</svg>`;
const RESULT_LABELS = ["Demande", "Pièce d'identité", "Justificatif de domicile", "Avis d'imposition"];
const RESULT_ROWS = {
  label: RESULTS_FILES.flatMap((f, fi) =>
    Array.from({ length: f.pages }, (_, i) => {
      const label = RESULT_LABELS[(fi + i) % RESULT_LABELS.length];
      return { id: `lab-${f.id}-${i}`, name: label, value: label, confidence: 0.99 - ((fi + i) % 5) * 0.04, document_id: f.id, document_name: f.name, pages: [resultPage(f, i + 1)], bounding_boxes: [resultBox(f, i + 1)] };
    }),
  ),
  entity: ["nom", "prénom", "date de naissance", "nationalité", "adresse", "numéro de dossier"].flatMap((name, n) =>
    RESULTS_FILES.flatMap((f, fi) =>
      Array.from({ length: 2 }, (_, i) => ({
        id: `ent-${n}-${f.id}-${i}`,
        name,
        value: `${name === "nom" ? "Iliev" : name === "prénom" ? "Marek" : `valeur ${name}`}${i ? " (bis)" : ""}`,
        confidence: 0.97 - ((n + i) % 4) * 0.05,
        document_id: f.id,
        document_name: f.name,
        pages: (i ? [1, 2] : [i + 1]).map((n) => resultPage(f, n)),
        bounding_boxes: (i ? [1, 2] : [i + 1]).map((n) => resultBox(f, n)),
      })),
    ),
  ),
};
const RESULTS_BREAKDOWN = RESULTS_FILES.map((f) => ({
  document_id: f.id,
  document_name: f.name,
  page_count: f.pages,
  classified_page_count: f.pages,
  entity_count: RESULT_ROWS.entity.filter((r) => r.document_id === f.id).length,
}));

// Journal d'événements d'un dossier (#169, #171), du plus récent au plus ancien.
const ALEX = { actor_id: "u1", actor_name: "Alex Martin" };
const CAMILLE = { actor_id: "u2", actor_name: "Camille Durand" };
const SYSTEM = { actor_id: null, actor_name: null };
const at = (days, hours, minutes) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(hours, minutes, 0, 0);
  return d.toISOString();
};
const event = (n, type, who, when, payload = {}) => ({ id: `ev-${n}`, type, ...who, created_at: when, payload });
const EVENTS = [
  event(1, "status_changed", ALEX, at(0, 10, 12), { from: { id: "st-2", name: "En instruction" }, to: { id: "st-5", name: "Clos" } }),
  event(2, "closed", ALEX, at(0, 10, 12), { status: { id: "st-5", name: "Clos" } }),
  event(3, "consulted", ALEX, at(0, 9, 55)),
  event(4, "document_downloaded", ALEX, at(0, 9, 40), { document_id: "gen-1", format: "pdf" }),
  event(5, "document_generated", ALEX, at(0, 9, 31), { document_id: "gen-1", version_number: 2, template_name: "Décision d'octroi", incomplete: false }),
  event(6, "analysis_finished", SYSTEM, at(-1, 17, 5)),
  event(7, "analysis_started", CAMILLE, at(-1, 16, 58), { analyse_version: "v1" }),
  event(8, "consulted", CAMILLE, at(-1, 14, 22)),
  event(9, "status_changed", CAMILLE, at(-1, 14, 20), { from: { id: "st-1", name: "À instruire" }, to: { id: "st-2", name: "En instruction" } }),
  event(10, "document_added", CAMILLE, at(-3, 11, 2), { document_id: "doc-1", mimetype: "application/pdf", size: 482113 }),
  event(11, "analyse_assigned", CAMILLE, at(-3, 10, 58), { analyse_id: "an-subv", analyse_name: "Instruction subventions" }),
  event(12, "created", CAMILLE, at(-3, 10, 55), { analyse_id: null }),
];

// Tableau de suivi (#173) : dossiers de trois analyses, servis par `GET /api/tracking` comme le fait le backend.
const USERS = [
  { id: "u1", name: "Alex Martin" },
  { id: "u2", name: "Camille Durand" },
  { id: "u3", name: "Samir Benali" },
  { id: "u4", name: "Léa Petit" },
];
const TRACKED_ANALYSES = [
  { id: ANALYSE_ID, name: "Instruction subventions", statuses: STATUSES },
  { id: "an-urba", name: "Urbanisme", statuses: STATUSES.map((s) => ({ ...s, id: `urba:${s.id}` })) },
  { id: "an-cmd", name: "Commande publique", statuses: STATUSES.map((s) => ({ ...s, id: `cmd:${s.id}` })) },
];
const SUBJECTS = {
  [ANALYSE_ID]: ["Subvention association Les Mouettes", "Convention de partenariat culturelle", "Aide au projet sportif jeunesse", "Subvention festival de quartier", "Aide aux séjours de vacances", "Soutien à une résidence d'artistes"],
  "an-urba": ["Permis de construire", "Déclaration préalable de travaux", "Certificat d'urbanisme", "Permis d'aménager"],
  "an-cmd": ["Marché fournitures bureau", "Marché entretien espaces verts", "Accord-cadre fournitures scolaires", "Marché de nettoyage"],
};
// Colonnes personnalisées du suivi (#173) : celles de l'analyse « Instruction subventions », modifiables le temps du
// scénario, avec leurs versions ; les valeurs sont portées par les dossiers simulés.
const SUBV_FIELDS = () => [
  { id: "f_montant01", name: "Montant demandé", definition: "Montant de l'aide sollicité par le demandeur, tel qu'indiqué dans le formulaire.", type: "amount", required: false, default_value: null, choices: [], currency: "EUR" },
  { id: "f_service01", name: "Service", definition: "Service instructeur en charge du dossier.", type: "choice", required: true, default_value: "Culture", choices: ["Culture", "Sport", "Social", "Éducation"], currency: "EUR" },
  { id: "f_depot0001", name: "Date de dépôt", definition: "Date de réception du dossier complet. Sert de point de départ au délai d'instruction.", type: "date", required: false, default_value: null, choices: [], currency: "EUR" },
  { id: "f_priorite1", name: "Prioritaire", definition: "À cocher quand le dossier doit être traité avant les autres.", type: "boolean", required: false, default_value: false, choices: [], currency: "EUR" },
];
let customFields = SUBV_FIELDS();
let customVersions = [{ id: "cfv-1", created_at: iso(-15), content: SUBV_FIELDS().slice(0, 2) }];
const SERVICES = ["Culture", "Sport", "Social", "Éducation"];

const TRACKED = TRACKED_ANALYSES.flatMap((analyse, a) =>
  SUBJECTS[analyse.id].map((subject, i) => {
    const n = a * 10 + i;
    const status = analyse.statuses[(n * 2) % analyse.statuses.length];
    const closed = status.is_final;
    return {
      id: `trk-${n}`,
      ref: n + 1,
      name: `${subject} n°${100 + n}`,
      analyse,
      status,
      assignee: n % 3 === 0 ? null : USERS[n % USERS.length],
      visibility: n % 4 === 1 ? "restricted" : "analyse",
      due_at: n % 5 === 4 ? null : dayKey((n % 7) * 9 - 12),
      closed,
      created_at: iso(-30 + n),
      last_activity_at: iso(-(n % 9)),
      values:
        analyse.id === ANALYSE_ID
          ? { f_montant01: 800 + n * 350, f_service01: SERVICES[n % 4], f_depot0001: dayKey(-40 + n * 3), f_priorite1: n % 3 === 0 }
          : {},
    };
  }),
);
const dueOfTracked = (d) => {
  if (!d.due_at) return null;
  const days_left = daysUntil(d.due_at);
  if (d.closed) return { level: "closed", days_left, color: null };
  if (days_left < 0) return { level: "overdue", days_left, color: DEFAULT_DUE.thresholds.overdue_color };
  const step = [...DEFAULT_DUE.thresholds.steps].sort((x, y) => x.days - y.days).find((s) => days_left <= s.days);
  return { level: step ? "soon" : "ok", days_left, color: step ? step.color : DEFAULT_DUE.thresholds.far_color };
};
const trackingRow = (d) => ({
  id: d.id,
  reference: `DOS-${new Date().getFullYear()}-${String(d.ref).padStart(4, "0")}`,
  name: d.name,
  analyse: { id: d.analyse.id, name: d.analyse.name },
  status: d.status,
  assignee: d.assignee,
  visibility: d.visibility,
  due_at: d.due_at,
  due: dueOfTracked(d),
  created_at: d.created_at,
  last_activity_at: d.last_activity_at,
  values: d.analyse.id === ANALYSE_ID ? Object.fromEntries(Object.entries(d.values).filter(([id]) => customFields.some((f) => f.id === id))) : {},
});
// Notifications (#174) : `GET /api/notifications` et marquage comme lu.
const notificationsOf = () => {
  const hoursAgo = (h) => new Date(Date.now() - h * 3_600_000).toISOString();
  const open = TRACKED.filter((d) => !d.closed);
  const make = (n, kind, d, message, hours, read = false) => ({ id: `ntf-${n}`, kind, category: { assigned: "assignment", overdue: "deadline", due_soon: "deadline", status_changed: "status", analysis_done: "analysis", analysis_failed: "analysis" }[kind], dossier_id: d.id, dossier_name: d.name, message, created_at: hoursAgo(hours), read_at: read ? hoursAgo(hours - 1) : null });
  return [
    make(1, "overdue", open[0], "L'échéance du dossier est dépassée.", 2),
    make(2, "assigned", open[1], "Ce dossier vous a été affecté par Camille Durand.", 5),
    make(3, "analysis_done", open[2], "L'analyse que vous avez lancée est terminée.", 26),
    make(4, "status_changed", open[3], "Statut passé à « À valider » par Samir Benali.", 50, true),
    { ...make(5, "assigned", open[0], "Ce dossier vous a été affecté par Camille Durand.", 70, true), dossier_id: null, dossier_name: null, accessible: false },
  ];
};
let NOTIFICATIONS = notificationsOf();

// Accès des dossiers (#177), modifiable le temps du scénario.
const ACCESS = { "dos-3": { visibility: "restricted", groups: ["/service-culture"] } };
const accessState = (id, canEdit) => {
  const current = ACCESS[id] ?? { visibility: "analyse", groups: [] };
  return {
    visibility: current.visibility,
    groups: current.groups.map((path) => ({ path, granted_by: "u1", created_at: iso(-3) })),
    can_edit: canEdit,
    available_groups: ["/service-culture", "/service-sport"],
  };
};

// Créneaux de traitement (#174) : `PUT` / `DELETE /api/dossiers/{id}/slot`, gardés le temps du scénario.
const SLOTS = new Map();

// Tableau de bord (#174) : `GET /api/dashboard`, bâti sur les mêmes dossiers que le suivi.
function dashboardPayload(isAdmin) {
  const open = TRACKED.filter((d) => !d.closed);
  const urgencies = open
    .filter((d) => d.due_at && ["soon", "overdue"].includes(dueOfTracked(d).level))
    .sort((a, b) => a.due_at.localeCompare(b.due_at))
    .map((d) => {
      const due = dueOfTracked(d);
      return { dossier_id: d.id, dossier_name: d.name, analyse_id: d.analyse.id, analyse_name: d.analyse.name, status_label: d.status.name, due_at: d.due_at, level: due.level, days_left: due.days_left, color: due.color, slot: SLOTS.get(d.id) ?? null };
    });
  const counts = new Map();
  for (const d of open) counts.set(d.status.id, { status_id: d.status.id, label: d.status.name, analyse_name: d.analyse.name, count: (counts.get(d.status.id)?.count ?? 0) + 1 });
  const hoursAgo = (h) => new Date(Date.now() - h * 3_600_000).toISOString();
  const first = open[0], second = open[1], third = open[2], fourth = open[3];
  return {
    stats: { total_dossiers: TRACKED.length, closed_dossiers: TRACKED.length - open.length, completed_this_week: 9, completed_prev_week: 6, weekly_closed: [5, 8, 6, 9], avg_processing_days: 2.4, on_time_rate: 0.87 },
    urgencies,
    status_counts: [...counts.values()],
    unassigned: isAdmin ? open.filter((d) => !d.assignee).map((d) => ({ dossier_id: d.id, dossier_name: d.name, analyse_name: d.analyse.name, created_at: d.created_at })) : null,
    activity: [
      { id: "act-1", kind: "analysis_done", dossier_id: first.id, dossier_name: first.name, message: "Analyse terminée", at: hoursAgo(1) },
      { id: "act-2", kind: "status_changed", dossier_id: second.id, dossier_name: second.name, message: "Statut : À instruire → En instruction, par Camille Durand", at: hoursAgo(4) },
      { id: "act-3", kind: "document_added", dossier_id: third.id, dossier_name: third.name, message: "Document ajouté, par Samir Benali", at: hoursAgo(22) },
      { id: "act-4", kind: "analysis_failed", dossier_id: fourth.id, dossier_name: fourth.name, message: "L'analyse a échoué", at: hoursAgo(47) },
    ],
  };
}

function trackingPage(params) {
  const get = (k) => params.get(k);
  const analyses = params.getAll("analyse_id");
  const search = (get("search") ?? "").toLowerCase();
  let rows = TRACKED.filter((d) => {
    if (analyses.length && !analyses.includes(d.analyse.id)) return false;
    if (get("status_id") && d.status.id !== get("status_id")) return false;
    const category = get("status_category");
    if (category === "initial" && !d.status.is_initial) return false;
    if (category === "final" && !d.status.is_final) return false;
    if (category === "progress" && (d.status.is_initial || d.status.is_final)) return false;
    if (get("access") && d.visibility !== get("access")) return false;
    const assignee = get("assignee");
    if (assignee === "none" && d.assignee) return false;
    if (assignee === "me" && d.assignee?.id !== "u1") return false;
    if (assignee && !["none", "me"].includes(assignee) && d.assignee?.id !== assignee) return false;
    const due = get("due");
    if (due) {
      if (d.closed) return false;
      const left = d.due_at ? daysUntil(d.due_at) : null;
      if (due === "none" ? left !== null : left === null || (due === "overdue" ? left >= 0 : left < 0 || left > Number(due))) return false;
    }
    return !search || d.name.toLowerCase().includes(search) || trackingRow(d).reference.toLowerCase().includes(search);
  });
  const sortKey = get("sort") ?? "created_at";
  const dir = get("direction") === "asc" ? 1 : -1;
  const value = (d) => ({ reference: d.ref, name: d.name.toLowerCase(), analyse: d.analyse.name, status: d.status.position, assignee: d.assignee?.name ?? null, due: d.due_at, created_at: d.created_at, last_activity_at: d.last_activity_at })[sortKey];
  rows = [...rows].sort((x, y) => {
    const a = value(x), b = value(y);
    if (a === null) return b === null ? 0 : 1; // les valeurs absentes restent en dernier
    if (b === null) return -1;
    return (a < b ? -1 : a > b ? 1 : 0) * dir;
  });
  const size = Number(get("page_size") ?? 20);
  const page = Number(get("page") ?? 1);
  return { items: rows.slice((page - 1) * size, page * size).map(trackingRow), total: rows.length, page, page_size: size, pages: Math.max(1, Math.ceil(rows.length / size)) };
}

// Les analyses supplémentaires (Urbanisme, Commande publique) ne servent qu'au tableau de suivi ; ailleurs elles
// changeraient les libellés des filtres de statut des autres captures.
let trackingScenario = false;

const page_of = (items) => ({ items, total: items.length, page: 1, page_size: 20, pages: 1 });

function api(role) {
  // Statuts de l'analyse, modifiables : un statut encore utilisé ne peut pas être supprimé sans remplaçant.
  let statuses = STATUSES.map((s) => ({ ...s }));
  let versions = [
    {
      id: "ver-1",
      created_at: iso(-12),
      content: STATUSES.filter((s) => s.id !== "st-3" && s.id !== "st-4").map((s, i) => ({ ...s, position: i, is_final: s.id === "st-5" })),
    },
  ];
  let dueSettings = JSON.parse(JSON.stringify(DEFAULT_DUE));
  let dueVersions = [{ id: "dv-1", created_at: iso(-20), content: { default_due_days: null, thresholds: { far_color: "#18753c", steps: [{ days: 10, color: "#ce0500" }], overdue_color: "#8a0000" } } }];
  const withDue = (d) => ({ ...d, due: dueOf(d, dueSettings.thresholds), closed_before_due: null });
  const analyseOut = () => ({
    id: ANALYSE_ID,
    name: "Instruction subventions",
    description: "Instruction des demandes de subvention des associations.",
    created_at: iso(-90),
    classification: { prompt: "", prompt_versions: [], labels: [], labels_versions: [] },
    extraction: { prompt: "", prompt_versions: [], entities: [], entities_versions: [] },
    statuses,
    statuses_versions: versions,
    due_settings: dueSettings,
    due_settings_versions: dueVersions,
    custom_fields: customFields,
    custom_fields_versions: customVersions,
    agents: [],
  });
  return (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/api/auth/me") return json(profiles[role]);
    if (path === "/api/cgu/acceptance") return json({ accepted: true, cgu: null });
    if (path === "/api/cgu") return json({}, 404);
    if (path === "/api/analyses") {
      return json(page_of([{ id: ANALYSE_ID, name: "Instruction subventions", description: "Instruction des demandes de subvention des associations.", created_at: iso(-90), agent_count: 2, statuses }, ...(trackingScenario ? TRACKED_ANALYSES.slice(1) : []).map((a) => ({ id: a.id, name: a.name, description: "", created_at: iso(-60), agent_count: 1, statuses: a.statuses }))]));
    }
    if (path === `/api/analyses/${ANALYSE_ID}`) return json(analyseOut());
    if (path === `/api/analyses/${ANALYSE_ID}/statuses` && method === "PUT") {
      const body = route.request().postDataJSON();
      const kept = new Set(body.statuses.map((x) => x.id));
      const removedInUse = statuses.filter((x) => !kept.has(x.id) && dossiers.some((d) => d.workflow_status?.id === x.id));
      const missing = removedInUse.filter((x) => !body.replacements?.[x.id]);
      if (missing.length) {
        return json(
          { detail: { code: "status_in_use", message: "Des statuts supprimés sont encore utilisés par des dossiers.", statuses: missing.map((x) => ({ id: x.id, name: x.name, dossier_count: dossiers.filter((d) => d.workflow_status?.id === x.id).length })) } },
          409,
        );
      }
      versions = [{ id: `ver-${versions.length + 1}`, created_at: new Date().toISOString(), content: statuses }, ...versions];
      statuses = body.statuses.map((x, i) => ({ id: x.id ?? `st-new-${i}`, name: x.name, color: x.color, position: i, is_initial: x.is_initial, is_final: x.is_final }));
      return json(analyseOut());
    }
    if (path === `/api/analyses/${ANALYSE_ID}/due-settings` && method === "PUT") {
      const body = route.request().postDataJSON();
      dueVersions = [{ id: `dv-${dueVersions.length + 1}`, created_at: new Date().toISOString(), content: dueSettings }, ...dueVersions];
      dueSettings = body;
      return json(analyseOut());
    }
    if (path === "/api/tracking") return json(trackingPage(url.searchParams));
    // Colonnes personnalisées (#173) : définitions (versionnées) et valeurs validées par type.
    if (path === `/api/analyses/${ANALYSE_ID}/custom-fields` && method === "PUT") {
      const body = route.request().postDataJSON();
      customVersions = [{ id: `cfv-${customVersions.length + 1}`, created_at: new Date().toISOString(), content: customFields }, ...customVersions];
      customFields = body.fields.map((f, i) => ({ ...f, id: f.id ?? `f_new${i}${Date.now() % 100000}` }));
      return json(analyseOut());
    }
    const valueMatch = path.match(/^\/api\/dossiers\/(trk-\d+)\/custom-values\/(f_\w+)$/);
    if (valueMatch && method === "PUT") {
      const { value } = route.request().postDataJSON();
      const field = customFields.find((f) => f.id === valueMatch[2]);
      if (field?.type === "amount" && typeof value === "number" && value < 0) {
        return json({ detail: { code: "invalid_value", message: "Saisissez un montant positif." } }, 422);
      }
      const target = TRACKED.find((d) => d.id === valueMatch[1]);
      if (target) target.values[valueMatch[2]] = value;
      return json({ field_id: valueMatch[2], value });
    }
    // Accès aux dossiers (#177) : lecture, simulation et enregistrement ; un seul dossier de démonstration (dos-3).
    const accessMatch = path.match(/^\/api\/dossiers\/(dos-\d+)\/access$/);
    if (accessMatch && method === "GET") return json(accessState(accessMatch[1], role === "admin"));
    if (accessMatch && method === "PUT") {
      const body = route.request().postDataJSON();
      const dryRun = url.searchParams.get("dry_run") === "true";
      const losing = !body.group_paths.includes("/service-culture") && body.visibility === "restricted";
      const person = losing ? { id: "u2", name: "Camille Durand" } : null;
      if (!dryRun) ACCESS[accessMatch[1]] = { visibility: body.visibility, groups: body.group_paths };
      return json({ ...accessState(accessMatch[1], true), assignee_unassigned: !!person, unassigned_person: person });
    }
    if (path === "/api/dossiers/bulk-access" && method === "PUT") {
      const body = route.request().postDataJSON();
      return json({ updated: body.dossier_ids.length, unchanged: 0, unassigned: 1 });
    }
    if (path === "/api/dashboard") return json(dashboardPayload(role === "admin"));
    if (path === "/api/notifications" && method === "GET") return json(NOTIFICATIONS);
    if (path === "/api/notifications/read-all" && method === "POST") {
      const unread = NOTIFICATIONS.filter((n) => !n.read_at);
      for (const n of unread) n.read_at = new Date().toISOString();
      return json({ marked: unread.length });
    }
    const readMatch = path.match(/^\/api\/notifications\/([\w-]+)\/read$/);
    if (readMatch && method === "POST") {
      const target = NOTIFICATIONS.find((n) => n.id === readMatch[1]);
      if (target && !target.read_at) target.read_at = new Date().toISOString();
      return route.fulfill({ status: 204 });
    }
    const slotMatch = path.match(/^\/api\/dossiers\/(trk-\d+)\/slot$/);
    if (slotMatch && method === "PUT") {
      const body = route.request().postDataJSON();
      const saved = { id: `slot-${slotMatch[1]}`, dossier_id: slotMatch[1], start: body.start, end: body.end, recurrence: body.recurrence ?? null, reminders: body.reminders ?? [], updated_at: new Date().toISOString() };
      SLOTS.set(slotMatch[1], saved);
      return json(saved);
    }
    if (slotMatch && method === "DELETE") {
      SLOTS.delete(slotMatch[1]);
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/users") return json(USERS);
    if (path === "/api/dossiers/bulk-assignee" && method === "PUT") {
      const body = route.request().postDataJSON();
      const person = USERS.find((u) => u.id === body.assignee_id) ?? null;
      let updated = 0;
      for (const d of TRACKED.filter((t) => body.dossier_ids.includes(t.id))) {
        if ((d.assignee?.id ?? null) !== (person?.id ?? null)) updated++;
        d.assignee = person;
      }
      return json({ updated, unchanged: body.dossier_ids.length - updated });
    }
    if (path === "/api/dossiers" && method === "GET") {
      const wanted = url.searchParams.get("workflow_status_id");
      const due = url.searchParams.get("due");
      let items = dossiers.map(withDue).filter((d) => !wanted || d.workflow_status?.id === wanted);
      if (due) {
        items = items.filter((d) => {
          if (d.closed_at) return false;
          if (due === "none") return !d.due_at;
          if (!d.due_at) return false;
          const days = daysUntil(d.due_at);
          return due === "overdue" ? days < 0 : days >= 0 && days <= Number(due);
        });
      }
      if (url.searchParams.get("sort") === "due") items.sort((a, b) => (a.due_at ?? "9999").localeCompare(b.due_at ?? "9999"));
      return json(page_of(items));
    }
    const dueMatch = path.match(/^\/api\/dossiers\/(dos-\d+)\/due-at$/);
    if (dueMatch && method === "PUT") {
      const target = dossiers.find((d) => d.id === dueMatch[1]);
      const next = route.request().postDataJSON().due_at;
      EVENTS.unshift(event(100 + EVENTS.length, "due_date_changed", ALEX, new Date().toISOString(), { from: target.due_at, to: next }));
      target.due_at = next;
      return json(withDue(target));
    }
    if (path === "/api/dossiers/dos-20") return json(withDue(RESULTS_DOSSIER));
    const pageMatch = path.match(/^\/api\/dossiers\/dos-20\/documents\/(doc-r\d)\/pages\/pg-doc-r\d-(\d+)(\/screenshot)?$/);
    if (pageMatch) {
      const file = RESULTS_FILES.find((f) => f.id === pageMatch[1]);
      const number = Number(pageMatch[2]);
      if (pageMatch[3]) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: resultPageSvg(file.name.replace(".pdf", "")) });
      return json({
        id: `pg-${file.id}-${number}`,
        page_number: number,
        width: 620,
        height: 877,
        content: "RÉPUBLIQUE FRANÇAISE\nPréfecture du Rhône\nDemande de renouvellement de titre de séjour\nNom : Iliev\nPrénom : Marek\nAdresse : 12 rue de la République, 69001 Lyon",
        has_screenshot: true,
        bounding_boxes: [resultBox(file, number)],
        document_id: file.id,
        document_name: file.name,
      });
    }
    if (path === "/api/dossiers/dos-20/results/breakdown") return json(RESULTS_BREAKDOWN);
    if (path === "/api/dossiers/dos-20/results") {
      const rows = RESULT_ROWS[url.searchParams.get("kind")] ?? [];
      const size = Number(url.searchParams.get("page_size") ?? 10);
      const page = Number(url.searchParams.get("page") ?? 1);
      return json({ items: rows.slice((page - 1) * size, page * size), total: rows.length, page, page_size: size, pages: Math.max(1, Math.ceil(rows.length / size)) });
    }
    const match = path.match(/^\/api\/dossiers\/(dos-\d+)$/);
    if (match) return json(withDue(dossiers.find((d) => `dos-${match[1].slice(4)}` === d.id) ?? dossiers[0]));
    if (path === "/api/dossiers/dos-3/events/actors") return json([ALEX, CAMILLE].map(({ actor_id, actor_name }) => ({ actor_id, actor_name })));
    if (path === "/api/dossiers/dos-3/events") {
      const types = url.searchParams.getAll("type");
      const actor = url.searchParams.get("actor_id");
      const wanted = EVENTS.filter((e) => (!types.length || types.includes(e.type)) && (!actor || e.actor_id === actor));
      const size = Number(url.searchParams.get("page_size") ?? 20);
      const page = Number(url.searchParams.get("page") ?? 1);
      return json({ items: wanted.slice((page - 1) * size, page * size), total: wanted.length, page, page_size: size, pages: Math.max(1, Math.ceil(wanted.length / size)) });
    }
    if (path === "/api/conversations") return json(page_of([]));
    if (path.startsWith("/api/reports") || path.startsWith("/api/me/tasks")) return json([]);
    if (path === "/api/me/stats") return json({});
    return json(page_of([]));
  };
}

async function newPage(browser, role, viewport = { width: 1280, height: 800 }) {
  const context = await browser.newContext({ viewport, locale: "fr-FR", timezoneId: "Europe/Paris" });
  await context.grantPermissions(["notifications"], { origin: baseUrl });
  const page = await context.newPage();
  await page.route("**/api/**", api(role));
  return page;
}

const out = (dir, file) => {
  const path = resolve(docsRoot, dir, file);
  mkdirSync(dirname(path), { recursive: true });
  return path;
};

const settle = (page, ms = 500) => page.waitForTimeout(ms);

/** Capture de la page entière. */
async function shot(page, dir, file) {
  await settle(page);
  await page.screenshot({ path: out(dir, file), fullPage: true });
  console.log(`✓ ${dir}/${file}`);
}

/** Capture d'une fenêtre (modale) ouverte. */
async function shotModal(page, dir, file) {
  await settle(page, 600);
  await page.locator(".fr-modal--opened .fr-modal__body").first().screenshot({ path: out(dir, file) });
  console.log(`✓ ${dir}/${file}`);
}

/** Capture de la modale du dessus quand plusieurs sont ouvertes (ex. la page source par-dessus une liste). */
async function shotTopModal(page, dir, file) {
  await settle(page, 600);
  await page.locator(".fr-modal--opened .fr-modal__body").last().screenshot({ path: out(dir, file) });
  console.log(`✓ ${dir}/${file}`);
}

async function closeModal(page) {
  await page.keyboard.press("Escape");
  await settle(page, 300);
}

/** Ouvre le menu « Options » du tableau de suivi s'il est fermé. */
async function openOptions(page) {
  const open = await page.locator("details.track__more").evaluate((el) => el.open);
  if (!open) await page.getByText("Options").click();
}

async function waitDashboard(page) {
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "networkidle" });
  await page.getByText("Mon agenda").waitFor();
  await settle(page, 600);
}

// ---------------------------------------------------------------------------
// Tableau de bord
// ---------------------------------------------------------------------------
/** Planifie un créneau pour le premier dossier de la section « À planifier » (les créneaux ne sont pas encore côté serveur). */
async function planSlot(page, start, end) {
  const toPlan = page.locator("details.cal__toplan");
  if (!(await toPlan.evaluate((el) => el.open))) await toPlan.locator("summary").click();
  await toPlan.getByRole("button", { name: "Planifier", exact: true }).first().click();
  await page.locator("#slot-start").fill(start);
  await page.locator("#slot-end").fill(end);
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await settle(page, 300);
}

async function dashboard(browser) {
  const dir = "tableau-de-bord";
  SLOTS.clear();
  NOTIFICATIONS = notificationsOf();
  const page = await newPage(browser, "admin", { width: 1280, height: 2000 });
  await waitDashboard(page);
  // Quelques créneaux pour montrer l'agenda du jour (enregistrés côté serveur).
  await page.getByRole("button", { name: "Jour", exact: true }).click();
  for (const [start, end] of [["09:00", "10:30"], ["11:00", "12:00"], ["14:00", "16:00"]]) await planSlot(page, start, end);

  await shot(page, dir, "01-tableau-de-bord.png");

  await page.getByRole("button", { name: "Mois", exact: true }).click();
  await shot(page, dir, "02-calendrier-du-mois.png");

  await page.getByRole("button", { name: "Liste", exact: true }).click();
  await shot(page, dir, "03-liste-des-urgences.png");

  await page.getByRole("button", { name: /Rechercher/ }).click();
  await shot(page, dir, "04-recherche-et-filtres.png");
  await page.getByRole("button", { name: /Rechercher/ }).click();

  // Planification d'un créneau
  await page.getByRole("button", { name: "Jour", exact: true }).click();
  await settle(page);
  await page.locator(".cal__block").first().click();
  await shotModal(page, dir, "05-planifier-un-creneau.png");

  await page.locator("#slot-repeat-select").selectOption("custom");
  await page.getByRole("button", { name: "Ajouter un rappel" }).click();
  await page.locator("select[id^='slot-rem-']").last().selectOption("custom");
  await shotModal(page, dir, "06-repetition-et-rappels-personnalises.png");
  await closeModal(page);

  // Indicateurs
  await page.getByRole("button", { name: /^\d+\s*Dossiers$/ }).click();
  await shotModal(page, dir, "07-indicateurs.png");
  await closeModal(page);

  // Notifications
  await page.getByRole("button", { name: /^Notifications/ }).click();
  await shotModal(page, dir, "08-notifications.png");
  await closeModal(page);

  // Non affectés et activité
  await page.getByRole("button", { name: /Dossiers à prendre en charge/ }).click();
  await shotModal(page, dir, "09-dossiers-a-prendre-en-charge.png");
  await closeModal(page);

  await page.getByRole("button", { name: "Activité récente" }).click();
  await shotModal(page, dir, "10-activite-recente.png");
  await closeModal(page);

  // Planification rapide : une heure libre de l'agenda, puis le dossier (deux clics).
  await page.getByRole("button", { name: "Jour", exact: true }).click();
  await settle(page);
  await page.getByRole("button", { name: "Planifier un dossier à 17:00" }).hover();
  await shot(page, dir, "11-invitation-a-planifier.png");
  await page.getByRole("button", { name: "Planifier un dossier à 17:00" }).click();
  await shot(page, dir, "12-planification-rapide.png");
  await page.locator(".qp__item").first().click();
  await shot(page, dir, "13-creneau-cree.png");

  // Déplacer le créneau en le glissant d'une heure et demie vers le bas.
  const moved = page.locator(".cal__block", { hasText: "17:00–18:00" });
  const box = await moved.boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + 10);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 10 + 66, { steps: 6 });
  await shot(page, dir, "14-deplacer-un-creneau.png");
  await page.mouse.up();
  await settle(page, 400);
  await page.locator(".cal__block", { hasText: "18:30–19:30" }).waitFor({ timeout: 3000 });
  console.log("✓ créneau déplacé en 18:30–19:30");

  // Le bouton du bloc ouvre le dossier sans passer par la replanification.
  await page.locator(".cal__block-open").first().click();
  await page.waitForURL(/\/dossiers\/[\w-]+$/, { timeout: 3000 });
  console.log("✓ le bouton du bloc ouvre le dossier");
  await page.goBack();
  await waitDashboard(page);
  await page.getByRole("button", { name: "Mois", exact: true }).click();

  // Changer de jour : glisser une pastille du mois vers le lendemain.
  await settle(page, 400);
  const chip = page.locator(".cal__cell--today .cal__chip--movable").first();
  const from = await chip.boundingBox();
  const tomorrow = await page.locator(".cal__cell--today + .cal__cell").boundingBox();
  await page.mouse.move(from.x + 10, from.y + 5);
  await page.mouse.down();
  await page.mouse.move(tomorrow.x + tomorrow.width / 2, tomorrow.y + tomorrow.height / 2, { steps: 8 });
  await shot(page, dir, "15-deplacer-vers-un-autre-jour.png");
  await page.mouse.up();
  await settle(page, 400);
  await page.locator(".cal__cell--today + .cal__cell .cal__chip").first().waitFor({ timeout: 3000 });
  console.log("✓ créneau déplacé au lendemain");

  await page.context().close();
}

// ---------------------------------------------------------------------------
// Tableau de suivi
// ---------------------------------------------------------------------------
async function tracking(browser) {
  trackingScenario = true;
  const dir = "tableau-de-suivi";
  const page = await newPage(browser, "admin", { width: 1800, height: 1900 });
  await page.goto(`${baseUrl}/analyses/${ANALYSE_ID}/suivi`, { waitUntil: "networkidle" });
  await page.getByText(/\d+ dossiers?/).first().waitFor();
  await settle(page, 700);
  await shot(page, dir, "01-onglet-suivi.png");

  await page.getByRole("button", { name: /Filtres/ }).click();
  await shot(page, dir, "02-filtres.png");
  await page.getByRole("button", { name: /Filtres/ }).click();

  // Sélection et affectation en lot
  const boxes = page.locator("tbody input[type=checkbox]");
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await shot(page, dir, "03-affectation-en-lot.png");
  await page.locator("#bulk-assignee").selectOption({ label: "Camille Durand" });
  await page.getByRole("button", { name: "Affecter", exact: true }).click();
  await page.getByText(/affectés? à Camille Durand/).waitFor();
  await settle(page, 400);
  await shot(page, dir, "12-affectation-confirmee.png");

  // Aide d'une colonne
  await page.getByRole("button", { name: "Aide sur la colonne Échéance" }).click();
  await shot(page, dir, "04-definition-d-une-colonne.png");
  await page.keyboard.press("Escape");

  // Menu Options + Colonnes
  await openOptions(page);
  await shot(page, dir, "05-menu-options.png");
  await page.getByRole("button", { name: /Colonnes/ }).first().click();
  await shotModal(page, dir, "06-choix-des-colonnes.png");
  await closeModal(page);

  // Champs personnalisés, puis historique après une modification
  await openOptions(page);
  await page.getByRole("button", { name: /Champs personnalisés/ }).click();
  await page.locator(".cf__head").first().click();
  await shotModal(page, dir, "07-champs-personnalises.png");
  await page.locator("input[id^='cf-name-']").first().fill("Montant sollicité");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await page.getByText(/Colonnes personnalisées enregistrées/).waitFor();
  await settle(page, 400);
  await openOptions(page);
  await page.getByRole("button", { name: /Champs personnalisés/ }).click();
  await page.getByText(/Historique des versions/).click();
  await shotModal(page, dir, "08-historique-des-champs.png");
  await closeModal(page);

  // Édition en cellule avec erreur de validation (montant négatif, refusé par le serveur)
  if (await page.locator("details.track__more").evaluate((el) => el.open)) await page.getByText("Options").click();
  await page.getByRole("button", { name: /^Modifier Montant sollicité/ }).first().click();
  await page.locator("tbody input.cell__input").first().fill("-5");
  await page.keyboard.press("Enter");
  await page.getByText("Saisissez un montant positif.").waitFor();
  await shot(page, dir, "09-edition-en-cellule.png");

  // Filtres sur les colonnes personnalisées
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Filtres/ }).click();
  await shot(page, dir, "13-filtres-sur-les-colonnes.png");
  await page.getByRole("button", { name: /Filtres/ }).click();

  // Vue transversale
  await page.goto(`${baseUrl}/suivi`, { waitUntil: "networkidle" });
  await page.getByText(/\d+ dossiers?/).first().waitFor();
  await settle(page, 700);
  await shot(page, dir, "10-vue-transversale.png");

  await page.getByRole("button", { name: /Filtres/ }).click();
  await page.getByLabel("Instruction subventions").check();
  await shot(page, dir, "11-vue-transversale-une-analyse.png");

  await page.context().close();
  trackingScenario = false;
}

// ---------------------------------------------------------------------------
// Accès aux dossiers par groupe
// ---------------------------------------------------------------------------
async function access(browser) {
  const dir = "acces-aux-dossiers";
  let page = await newPage(browser, "admin", { width: 1280, height: 1700 });

  await page.goto(`${baseUrl}/dossiers`, { waitUntil: "networkidle" });
  await page.getByText("Subvention association Les Mouettes").first().waitFor();
  await shot(page, dir, "01-pastille-restreint.png");

  await page.getByRole("button", { name: "Créer un dossier" }).click();
  await shotModal(page, dir, "02-creation-d-un-dossier-restreint.png");
  await closeModal(page);

  await page.goto(`${baseUrl}/dossiers/dos-3`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Accès au dossier" }).click();
  await page.getByText("Groupes associés").waitFor();
  await shotModal(page, dir, "03-acces-au-dossier.png");

  // Retrait d'un groupe : confirmation des pertes d'accès
  await page.getByLabel("Service culture").uncheck();
  await page.getByLabel("Service sport").check();
  await page.getByText(/perdra l'accès/).waitFor(); // la simulation du serveur nomme la personne affectée
  await shotModal(page, dir, "04-confirmation-des-pertes-d-acces.png");
  await closeModal(page);

  // Suivi : filtre Accès et définition en lot
  await page.goto(`${baseUrl}/suivi`, { waitUntil: "networkidle" });
  await page.getByText(/\d+ dossiers?/).first().waitFor();
  await page.getByRole("button", { name: "Tous", exact: true }).click();
  await settle(page);
  await page.getByRole("button", { name: /Filtres/ }).click();
  await page.locator("#tf-access").selectOption("restricted");
  await shot(page, dir, "05-suivi-dossiers-restreints.png");
  await page.locator("#tf-access").selectOption("");
  await page.locator("tbody input[type=checkbox]").nth(0).check();
  await page.locator("tbody input[type=checkbox]").nth(1).check();
  await page.getByRole("button", { name: "Définir l'accès" }).click();
  await shotModal(page, dir, "06-definir-l-acces-en-lot.png");
  await page.context().close();

  // Notification d'un dossier dont l'accès a été retiré
  page = await newPage(browser, "admin", { width: 1280, height: 1000 });
  await waitDashboard(page);
  await page.getByRole("button", { name: /^Notifications/ }).click();
  await shotModal(page, dir, "07-notification-d-un-dossier-non-accessible.png");
  await page.context().close();

  // Lecture seule pour un non-administrateur
  page = await newPage(browser, "user", { width: 1280, height: 1000 });
  await page.goto(`${baseUrl}/dossiers/dos-3`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Accès au dossier" }).click();
  await page.getByText("Groupes associés").waitFor();
  await shotModal(page, dir, "08-lecture-seule-pour-un-non-administrateur.png");
  await page.context().close();
}

// ---------------------------------------------------------------------------
// Statuts de dossier
// ---------------------------------------------------------------------------
async function workflowStatuses(browser) {
  const dir = "statuts-de-dossier";
  let page = await newPage(browser, "admin", { width: 1280, height: 1500 });

  await page.goto(`${baseUrl}/analyses/${ANALYSE_ID}/statuts`, { waitUntil: "networkidle" });
  await page.getByText("Statuts de dossier").first().waitFor();
  await shot(page, dir, "01-onglet-statuts.png");

  await page.getByText(/Historique des versions/).first().click();
  await shot(page, dir, "02-historique-des-statuts.png");

  // Supprimer un statut encore utilisé : le serveur répond 409 et on choisit un remplaçant.
  await page.getByRole("button", { name: "Supprimer Pièces manquantes" }).click();
  await page.getByRole("button", { name: "Enregistrer", exact: true }).first().click();
  await shotModal(page, dir, "03-remplacer-un-statut-utilise.png");
  await closeModal(page);

  // Dossiers : colonne Statut, filtre et tri
  await page.goto(`${baseUrl}/dossiers`, { waitUntil: "networkidle" });
  await page.getByText("Subvention association Les Mouettes").first().waitFor();
  await shot(page, dir, "04-liste-des-dossiers.png");

  await page.locator("#dossiers-status-filter").selectOption("st-2");
  await shot(page, dir, "05-filtre-par-statut.png");

  // Changer le statut depuis le dossier
  await page.goto(`${baseUrl}/dossiers/dos-3`, { waitUntil: "networkidle" });
  await page.getByText("Changer le statut du dossier").waitFor({ state: "attached" });
  await shot(page, dir, "06-statut-dans-le-dossier.png");
  await page.context().close();
}

// ---------------------------------------------------------------------------
// Historique du dossier
// ---------------------------------------------------------------------------
async function history(browser) {
  const dir = "historique-du-dossier";
  const page = await newPage(browser, "admin", { width: 1280, height: 1300 });

  await page.goto(`${baseUrl}/dossiers/dos-3`, { waitUntil: "networkidle" });
  await page.getByRole("link", { name: "Voir l'historique du dossier" }).waitFor();
  await page.getByRole("link", { name: "Voir l'historique du dossier" }).click();
  await page.getByText("Statut modifié").first().waitFor();
  await shot(page, dir, "01-historique-du-dossier.png");

  await page.getByRole("button", { name: /Consultations/ }).click();
  await settle(page);
  await shot(page, dir, "02-avec-les-consultations.png");
  await page.getByRole("button", { name: /Consultations/ }).click();

  await page.locator("#ef-actor").selectOption("u2");
  await settle(page);
  await shot(page, dir, "03-filtre-par-auteur.png");
  await page.locator("#ef-actor").selectOption("");

  for (const label of ["Création", "Analyse", "Documents"]) await page.getByRole("button", { name: new RegExp(label) }).click();
  await settle(page);
  await shot(page, dir, "04-filtre-par-type.png");
  await page.context().close();
}

// ---------------------------------------------------------------------------
// Échéance du dossier
// ---------------------------------------------------------------------------
async function dueDate(browser) {
  const dir = "echeance-du-dossier";
  const page = await newPage(browser, "admin", { width: 1280, height: 1900 });

  // Réglage par analyse : durée par défaut et seuils de couleur
  await page.goto(`${baseUrl}/analyses/${ANALYSE_ID}/statuts`, { waitUntil: "networkidle" });
  await page.getByText("Échéance des dossiers").first().waitFor();
  await page.getByText("Échéance des dossiers").first().scrollIntoViewIfNeeded();
  await shot(page, dir, "01-reglage-de-l-echeance.png");

  await page.getByRole("button", { name: "Ajouter un seuil" }).click();
  await page.getByLabel("Nombre de jours restants").last().fill("3");
  await page.getByRole("button", { name: "Enregistrer" }).last().click();
  await page.getByText(/Échéance enregistrée/).waitFor();
  await page.getByText(/Historique des versions/).last().click();
  await shot(page, dir, "02-historique-des-seuils.png");

  // Liste : colonne, filtre et tri
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/dossiers`, { waitUntil: "networkidle" });
  await page.getByText("Subvention association Les Mouettes").first().waitFor();
  await shot(page, dir, "03-liste-des-dossiers.png");
  await page.locator("#dossiers-due-filter").selectOption("overdue");
  await settle(page);
  await shot(page, dir, "04-filtre-echeance-depassee.png");
  await page.locator("#dossiers-due-filter").selectOption("");
  await page.locator("#dossiers-sort").selectOption("due");
  await settle(page);
  await shot(page, dir, "05-tri-par-echeance.png");

  // Dans le dossier : modifier l'échéance
  await page.goto(`${baseUrl}/dossiers/dos-3`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Modifier" }).waitFor();
  await shot(page, dir, "06-echeance-dans-le-dossier.png");
  await page.getByRole("button", { name: "Modifier" }).click();
  await page.getByLabel("Date d'échéance").fill(dayKey(21));
  await shot(page, dir, "07-modifier-l-echeance.png");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await settle(page);

  // Le changement est tracé dans l'historique
  await page.getByRole("link", { name: "Voir l'historique du dossier" }).click();
  await page.getByText("Échéance modifiée").first().waitFor();
  await shot(page, dir, "08-historique-du-dossier.png");
  await page.context().close();
}

// ---------------------------------------------------------------------------
// Détail des résultats d'un dossier (classification, entités)
// ---------------------------------------------------------------------------
async function results(browser) {
  const dir = "resultats-du-dossier";
  const page = await newPage(browser, "admin", { width: 1280, height: 1300 });
  await page.goto(`${baseUrl}/dossiers/dos-20`, { waitUntil: "networkidle" });
  await page.getByText("8/8 page(s) classifiée(s)").waitFor();
  await shot(page, dir, "01-cartes-de-resultats.png");

  await page.getByRole("button", { name: /Classification/ }).click();
  await page.getByText("Répartition par fichier").waitFor();
  await shotModal(page, dir, "02-detail-classification.png");
  await page.getByRole("button", { name: "Voir la page" }).first().click();
  await page.locator(".source-viewer__image").waitFor();
  await shotTopModal(page, dir, "05-page-d-une-classification.png");
  // « Fermer » de la page source : la liste reste ouverte dessous.
  await page.locator(".fr-modal--opened .fr-btn--close").last().click();
  await page.getByText("Répartition par fichier").waitFor();
  await closeModal(page);

  await page.getByRole("button", { name: /Entités/ }).click();
  await page.getByText("Répartition par fichier").waitFor();
  await shotModal(page, dir, "03-detail-entites.png");
  await page.locator(".fr-modal--opened .fr-pagination__link", { hasText: /^2$/ }).click();
  await shotModal(page, dir, "04-detail-entites-page-2.png");
  await page.getByRole("button", { name: "Voir la page" }).first().click();
  await page.locator(".source-viewer__image").waitFor();
  await shotTopModal(page, dir, "06-page-d-une-entite.png");
  await page.context().close();
}

const only = process.argv.slice(3);
const scenarios = { dashboard, tracking, access, statuses: workflowStatuses, history, due: dueDate, results };
const browser = await chromium.launch();
try {
  for (const [name, run] of Object.entries(scenarios)) {
    if (only.length === 0 || only.includes(name)) await run(browser);
  }
} finally {
  await browser.close();
}
