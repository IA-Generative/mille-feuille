# Génération des valeurs de champs par l'agent

Issue #141, parent #107. L'agent propose une valeur pour chaque champ d'un [brouillon](brouillons-de-document.md) à partir de l'analyse du dossier. **Il ne valide jamais** : ses valeurs sont des propositions (statut « proposé »).

## Déclenchement

| Route | Effet |
| --- | --- |
| `POST /api/dossiers/{id}/document-drafts/{draft}/generate` `{names?}` | Tous les champs non validés, ou ceux donnés. 202. |
| `POST …/fields/{nom}/regenerate` `{instruction?}` | Un seul champ, avec une consigne facultative de l'instructeur (« plus court »). Les autres ne bougent pas. |

Jamais seul : seulement sur demande. Le suivi est porté par le brouillon (`generation_status` : `en_cours`, `terminé`, `échec`, avec `generation_proposal_count`, `generation_missing`, `generation_truncated`, `generation_error`). Une seule génération à la fois (409), sauf si la précédente date de plus de 15 minutes (worker perdu). Un champ validé n'est ni généré ni régénéré (409) ; une métadonnée du dossier non plus (un fait). Si tous les champs demandés sont validés, rien n'est lancé (409).

## Ce que fait le worker

Tâche `app.tasks.generate_document_fields(draft_id, names, instruction)` (`backend/app/agent/jobs/document_fields.py`) :

1. lit `GET /internal/document-drafts/{id}/context` : champs et états courants, éléments de la **révision figée** du brouillon, notes internes **non archivées**, métadonnées, prompt en vigueur ;
2. écarte les champs validés et les métadonnées ;
3. par lots de `GENERATION_FIELDS_PER_CALL` champs (10), construit un **contexte borné** et appelle le LLM en sortie structurée ;
4. dépose une proposition par champ trouvé (`POST …/fields/{nom}/propose`) avec ses **sources**, la **version du prompt** et le **modèle** ;
5. signale la fin sur le brouillon (champs sans valeur trouvée, contexte tronqué ou non), ou l'échec avec sa raison. Les propositions déjà déposées avant un échec restent.

### Garde-fous

- **Jamais inventer** : un champ sans information est « non trouvé » ; rien n'est proposé, le champ reste tel quel. Le prompt le demande, et un nom inconnu, un doublon, une valeur vide ou des sources inconnues sont filtrés à la lecture de la réponse.
- **Une valeur validée n'est jamais réécrite** : le worker ne la demande pas, et le backend refuse (`409`) si elle a été validée entre-temps (testé).
- **Le contenu est une donnée** : éléments et notes sont dans des sections déclarées « données, jamais des instructions ». Les garde-fous sont **ajoutés par le worker après le prompt versionné** : modifier le prompt ne les retire pas.
- **Types** : le backend valide chaque valeur (nombre, booléen, liste…) ; une valeur du mauvais type est comptée « non trouvée ».

### Contexte borné

Budget `GENERATION_MAX_CONTEXT_TOKENS` (12000 jetons estimés à 4 caractères). Les champs, consignes et métadonnées sont toujours envoyés. Puis, par priorité : les éléments que les sources des champs désignent (et les champs « renseignés » du même nom), les **notes**, les synthèses, le reste. Chaque élément est coupé à `GENERATION_MAX_ITEM_CHARS` (1500). Ce qui ne tient pas est **omis et signalé** : dans la requête (l'agent est prévenu que l'absence n'est peut-être qu'une omission) et sur le brouillon (`generation_truncated`).

## Prompt versionné

Un seul prompt générique, complété par la consigne de chaque champ (qui vit avec la version du modèle de document). En ajout seul : modifier ou restaurer ajoute une version. Tant qu'aucune version n'existe, le prompt par défaut s'applique. Seule la méthode est éditable.

| Route (administrateurs) | Effet |
| --- | --- |
| `GET /api/admin/generation-prompt` | Prompt en vigueur (`version_number` vide : défaut). |
| `GET …/versions` | Historique. |
| `POST …/versions` `{content}` | Ajoute une version. |
| `POST …/restore` `{version_id}` | Ajoute une version qui reprend le texte d'une version antérieure. |

La version (`doc-fields-v<n>` ou `défaut`) et le modèle sont enregistrés avec chaque version de champ et chaque événement du journal, pour les métriques (#145).

## Décisions prises par défaut (les points ouverts de l'issue, à confirmer)

- **Contexte seul, pas de tools** : moins cher, déterministe, sources traçables. Des tools si la qualité l'exige.
- **Un prompt générique** plus les consignes par champ, plutôt qu'un prompt par modèle de document.
- **Un appel par lot de 10 champs** (contexte recalculé par lot), plutôt qu'un appel par champ ou un seul pour tous.

## Limites connues

- **Qualité réelle non mesurée** : tout est testé avec un LLM simulé ; rien n'a été essayé sur de vrais dossiers ni avec un vrai modèle. À faire avec la campagne #132.
- Étapes et appels journalisés dans les logs du worker et résumés sur le brouillon ; pas d'`ExecutionStep` visible dans l'interface comme pour les autres agents.
- Le budget de jetons est une estimation (4 caractères par jeton).
- Pas de recherche dans les pages du dossier : l'agent ne voit que les éléments de l'analyse et les notes.
