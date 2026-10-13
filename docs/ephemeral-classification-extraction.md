# Classification et extraction d'un document : guide d'utilisation (API + clé)

Ce guide montre comment classer les pages d'un document et en extraire les entités **avec une clé d'API**, en
`curl`. Chaque page / chaque document reçoit **deux résultats**, un par méthode :

| Route | Source `textual` | Autre source |
|---|---|---|
| Classification | texte de la page : OCR + description VLM + LLM | `visual` : apparence de la capture, **CLIP** (CPU) |
| Extraction | LLM, sur le texte des pages | `gliner` : **GLiNER2.5** (CPU), qui reçoit vos définitions comme descriptions |

Le principe général de l'API éphémère (TTL, purge, `persist`) est décrit dans [ephemeral-api.md](ephemeral-api.md).

Dans les exemples, la clé est dans `$KEY` et l'adresse du serveur dans `$BASE` (à remplacer) :

```bash
export BASE=https://mille-feuille.example.com
export KEY=la-cle-renvoyee-a-la-creation
```

## 1. Obtenir une clé d'API

Une clé d'API (« token d'application ») identifie un compte de service. Elle se crée **une fois**, depuis une session
connectée (Keycloak) ; elle n'est affichée **qu'à la création** : conservez-la.

**Depuis un terminal** (compte Keycloak avec mot de passe) : on obtient d'abord un jeton de session, puis on crée la
clé.

```bash
ACCESS=$(curl -sS -X POST "$BASE/api/auth/token" --get \
  --data-urlencode "username=prenom.nom" --data-urlencode "password=…" | jq -r .access_token)

curl -sS -X POST "$BASE/api/app-tokens" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"name": "mon-integration"}'
```

**Depuis le navigateur** : ouvrez `$BASE/api/auth/login`, connectez-vous, puis allez sur `$BASE/api/docs` (Swagger) et
exécutez `POST /api/app-tokens` avec `{"name": "mon-integration"}` (la session est réutilisée).

La réponse contient le champ `token`, la clé à conserver :

```json
{ "id": "6b0f…", "name": "mon-integration", "created_by": "…", "created_at": "…", "token": "k3J9…" }
```

Ensuite, **chaque appel** envoie la clé dans l'en-tête `X-App-Token` :

```bash
-H "X-App-Token: $KEY"
```

Sans clé valide : `401`. Une clé ne voit que les runs qu'elle a créés (un run d'une autre clé répond `404`).

## 2. Classification : labels, définitions, mono ou multi-label

### Lancer

```bash
curl -sS -X POST "$BASE/api/ephemeral/classifications" \
  -H "X-App-Token: $KEY" \
  -F "file=@./dossier-client.pdf" \
  -F 'labels=[
        {"name": "CNI",      "definition": "Carte nationale d identité française"},
        {"name": "RIB",      "definition": "Relevé d identité bancaire"},
        {"name": "Facture",  "definition": "Facture avec montants et TVA"}
      ]' \
  -F "multi_label=false"
```

| Champ (multipart) | Obligatoire | Rôle |
|---|---|---|
| `file` | oui | Un seul document (PDF, Office, image). |
| `labels` | oui | **JSON** : liste `[{"name", "definition"}]`, au moins un label. |
| `multi_label` | non (`false`) | `false` : un seul label par page et par source. `true` : un ou plusieurs. |
| `classification_prompt` | non | Consigne complémentaire pour la classification textuelle (LLM). |
| `persist` | non (`false`) | `true` : conserve le run indéfiniment au lieu de le purger. |
| `?ttl_hours=48` | non (24) | Durée de conservation du **résultat** après la fin du run (1 à 17520). |

Réponse `201` :

```json
{ "run_id": "0c6e2f1e-3b0a-4f0e-9d65-2f5b1c9f7a10" }
```

### Lire le résultat

Le traitement est asynchrone : relancez le `GET` jusqu'à ce que `status` vaille `terminé` (ou `échec`).

```bash
RUN=0c6e2f1e-3b0a-4f0e-9d65-2f5b1c9f7a10

curl -sS "$BASE/api/ephemeral/classifications/$RUN" -H "X-App-Token: $KEY" | jq
```

Statuts : `en_attente`, `en_cours`, `terminé`, `arrêté`, `échec` (alors `error` contient le message). Un script qui
attend la fin est donné en fin de document.

```json
{
  "run_id": "0c6e2f1e-3b0a-4f0e-9d65-2f5b1c9f7a10",
  "status": "terminé",
  "error": null,
  "expires_at": "2026-10-14T10:32:00Z",
  "documents": [
    {
      "name": "dossier-client.pdf",
      "pages": [
        {
          "page_number": 1,
          "labels": [
            { "name": "CNI", "confidence": 0.96, "source": "textual" },
            { "name": "CNI", "confidence": 0.99, "source": "visual" }
          ]
        },
        {
          "page_number": 2,
          "labels": [
            { "name": "RIB", "confidence": 0.91, "source": "textual" },
            { "name": "Facture", "confidence": 0.62, "source": "visual" }
          ]
        }
      ]
    }
  ]
}
```

Comment le lire :

- `labels` est **une liste par page** : les labels `textual` d'abord, puis les `visual`, chacun trié par confiance
  décroissante. Ici la page 2 est classée « RIB » par le texte mais « Facture » par l'apparence : c'est l'intérêt
  d'avoir les deux.
- **Filtrez sur `source`** plutôt que de supposer que les deux sont présents. Une page n'a pas de label `visual`
  si elle n'a pas de capture ou si CLIP a échoué sur elle (la classification textuelle n'en est jamais affectée).
- Avec `multi_label=true`, chaque source peut renvoyer plusieurs labels. En visuel, un label est retenu à partir de
  0,25 de probabilité (le meilleur est toujours retourné).
- La confiance `visual` est une probabilité relative **entre vos labels** (softmax) : elle est élevée dès qu'il y a peu
  de labels, même si aucun ne convient vraiment. Elle ne se compare pas directement à la confiance `textual`.

Ne garder qu'une source avec `jq` :

```bash
curl -sS "$BASE/api/ephemeral/classifications/$RUN" -H "X-App-Token: $KEY" \
  | jq '[.documents[].pages[] | {page: .page_number, visual: [.labels[] | select(.source=="visual")]}]'
```

### Conseils pour CLIP (source `visual`)

CLIP compare l'image de la page au texte `nom: définition` de chaque label. Il a surtout vu de l'anglais et ne lit
que 77 jetons : des **noms et définitions courts et descriptifs**, avec des mots que l'on voit sur le document,
donnent de meilleurs résultats que de longues définitions, qui sont coupées.

## 3. Extraction d'entités : définitions et résultat par page

### Lancer

```bash
curl -sS -X POST "$BASE/api/ephemeral/extractions" \
  -H "X-App-Token: $KEY" \
  -F "file=@./dossier-client.pdf" \
  -F 'entities=[
        {"name": "nom",            "definition": "Nom de famille de la personne", "type": "texte"},
        {"name": "date_naissance", "definition": "Date de naissance",             "type": "date"},
        {"name": "adresse",        "definition": "Adresse postale complète",      "type": "texte"},
        {"name": "montant",        "definition": "Montant en euros",              "type": "nombre"}
      ]'
```

| Champ (multipart) | Obligatoire | Rôle |
|---|---|---|
| `file` | oui | Un seul document. |
| `entities` | oui | **JSON** : liste `[{"name", "definition", "type"}]`, au moins une entité. |
| `extraction_prompt` | non | Consigne complémentaire pour l'extraction par le LLM. |
| `persist`, `?ttl_hours=` | non | Comme pour la classification. |

`type` : `texte`, `date`, `nombre`, `booléen` ou `identifiant`. **La `definition` est importante** : c'est elle que
GLiNER reçoit comme description de l'entité (le LLM aussi). Les entités de type `booléen` ne sont extraites que par
le LLM : GLiNER extrait du texte présent dans le document, pas des oui/non.

Réponse `201` : `{ "run_id": "…" }`.

### Lire le résultat

```bash
curl -sS "$BASE/api/ephemeral/extractions/$RUN" -H "X-App-Token: $KEY" | jq
```

```json
{
  "run_id": "…",
  "status": "terminé",
  "error": null,
  "expires_at": "2026-10-14T10:32:00Z",
  "documents": [
    {
      "name": "dossier-client.pdf",
      "pages": [
        {
          "page_number": 1,
          "entities": [
            { "name": "nom", "value": "Dupont", "confidence": 0.9, "source": "textual", "pages": [1, 2] },
            { "name": "nom", "value": "Dupont", "confidence": 0.97, "source": "gliner", "pages": [1, 2] },
            { "name": "date_naissance", "value": "12 mars 1985", "confidence": 0.99, "source": "gliner", "pages": [1] }
          ]
        },
        {
          "page_number": 2,
          "entities": [
            { "name": "nom", "value": "Dupont", "confidence": 0.9, "source": "textual", "pages": [1, 2] },
            { "name": "nom", "value": "Dupont", "confidence": 0.97, "source": "gliner", "pages": [1, 2] }
          ]
        }
      ]
    }
  ]
}
```

Comment le lire :

- Les entités sont **rangées par page**. Une entité trouvée sur plusieurs pages apparaît sur **chacune d'elles**, et
  `pages` donne **toutes** ses pages (ici `[1, 2]`).
- Les entités `textual` (LLM) viennent d'abord, puis les `gliner`. La même valeur peut apparaître avec les deux
  sources : c'est un signal de fiabilité.
- GLiNER ne renvoie que ce qui est **littéralement dans le texte** de la page, au-dessus d'une confiance de 0,5 ; le LLM
  peut reformuler ou normaliser la valeur.
- Côté GLiNER, une même valeur trouvée sur plusieurs pages (casse ignorée) est fusionnée en une seule entité, avec la
  meilleure confiance.

Valeurs de chaque entité, toutes sources confondues :

```bash
curl -sS "$BASE/api/ephemeral/extractions/$RUN" -H "X-App-Token: $KEY" \
  | jq '[.documents[].pages[].entities[] | {name, value, source}] | unique'
```

## 4. Nettoyage, arrêt, erreurs

```bash
# Arrêter un run en cours
curl -sS -X POST "$BASE/api/ephemeral/runs/$RUN/stop" -H "X-App-Token: $KEY"

# Supprimer le run et son résultat tout de suite (sans attendre le TTL)
curl -sS -X DELETE "$BASE/api/ephemeral/runs/$RUN" -H "X-App-Token: $KEY"
```

Sans `persist=true`, le document, ses pages et l'analyse créée pour l'appel sont **supprimés dès la fin du run** ; seul
le résultat reste lisible jusqu'à `expires_at`.

| Code | Cause |
|---|---|
| `400` | `ttl_hours` hors bornes (1 à 17520). |
| `401` | Clé absente ou invalide. |
| `404` | Run inconnu, expiré, ou créé par une autre clé. |
| `422` | `labels` / `entities` : JSON invalide, liste vide, champ manquant ou `type` inconnu ; ou `file` manquant. |

## 5. Exemple complet (script)

```bash
#!/usr/bin/env bash
# Usage : BASE=… KEY=… ./classer.sh mon-document.pdf
set -euo pipefail
: "${BASE:?}" "${KEY:?}"
H=(-H "X-App-Token: $KEY")

RUN=$(curl -sS -X POST "$BASE/api/ephemeral/classifications" "${H[@]}" \
  -F "file=@$1" \
  -F 'labels=[{"name":"CNI","definition":"Carte nationale d identité"},{"name":"RIB","definition":"Relevé d identité bancaire"}]' \
  -F multi_label=false | jq -r .run_id)

while :; do
  OUT=$(curl -sS "$BASE/api/ephemeral/classifications/$RUN" "${H[@]}")
  STATUS=$(jq -r .status <<<"$OUT")
  [[ "$STATUS" == "en_attente" || "$STATUS" == "en_cours" ]] || break
  sleep 3
done

[[ "$STATUS" == "terminé" ]] || { jq -r '.error // .status' <<<"$OUT" >&2; exit 1; }
jq -r '.documents[].pages[] | "page \(.page_number): " + ([.labels[] | "\(.name) (\(.source), \(.confidence))"] | join(", "))' <<<"$OUT"
```

Le même script fonctionne pour l'extraction en remplaçant `classifications` par `extractions` et le champ `labels` par
`entities`.

## Pour les exploitants

Les deux sources supplémentaires tournent **sur CPU**, dans les workers dédiés `worker/classification` (CLIP) et
`worker/extraction` (GLiNER2.5), qui embarquent leur modèle dans l'image (rien n'est téléchargé au démarrage) ; prévoir
~1,5 Go de mémoire chacun. Elles se désactivent sans toucher au code avec `CLIP_ENABLED=false` et
`GLINER_ENABLED=false` : l'API répond alors avec la seule source `textual`. Détails dans les README des workers.
