# Worker `document_render`

Remplit un **modèle ODT** avec des valeurs, puis produit un **PDF** avec LibreOffice (issue #146, parent #107 : document de fin d'instruction).

- **Remplissage** : moteur maison (`app/odt_template.py`, lxml + Jinja en bac à sable). LibreOffice n'intervient pas ici.
- **PDF** : `soffice --headless` (`app/pdf.py`), uniquement pour l'aperçu et l'export.
- **Pas d'édition en ligne** (WOPI/Collabora écartés) : on édite les valeurs dans le formulaire, l'aperçu est le PDF.

## Tâches Celery (file `document_render`)

| Tâche | Rôle |
| --- | --- |
| `inspect_template(template_key)` | **Contrôle d'un modèle à l'import** : ses champs (triés, variables de boucle exclues), les polices qu'il utilise et des avertissements (voir plus bas). Un modèle invalide est une erreur. |
| `extract_template_fields(template_key)` | Liste seulement les champs du modèle (ancienne tâche, conservée ; le backend utilise `inspect_template`). |
| `render_document(template_key, values, output_prefix, with_pdf=True)` | Dépose `<prefix>.odt` (et `<prefix>.pdf`) dans S3, renvoie les clés. |
| `render_preview(template_key, values, output_key)` | Dépose seulement le PDF. |

Un champ sans valeur est une **erreur** (`MissingValueError` nommant le champ) : on ne génère jamais un document à trous. Rien n'est déposé en cas d'échec.

## Écrire un modèle (dans LibreOffice Writer)

- Champ : `{{ nom }}`, ou `{{ dossier.adresse }}` pour un objet. Fonctionne dans le corps, les tableaux et les en-têtes/pieds de page.
- LibreOffice coupe parfois un champ en plusieurs morceaux de style (`{{ pre` + `nom }}`) : c'est recollé automatiquement ; le champ prend le style du premier morceau.
- Répéter des **lignes de tableau** : une ligne ne contenant que `{%tr for e in entites %}`, la ligne modèle avec `{{ e.nom }}`, une ligne `{%tr endfor %}`. Les lignes de contrôle disparaissent.
- Répéter des **paragraphes** : `{%p for … %}` / `{%p endfor %}` ; des **puces** : `{%li for … %}` / `{%li endfor %}` — chacun seul dans son paragraphe.
- Dans un même paragraphe : `{% if … %}…{% endif %}` et `{% for … %}…{% endfor %}` classiques.
- Les balises de bloc (`{%tr`, `{%p`, `{%li`) doivent être **seules** dans leur ligne/paragraphe/puce ; sinon erreur explicite.
- Les valeurs sont échappées (`& < >`), les retours à la ligne, tabulations et espaces multiples sont conservés.
- Expressions dangereuses (`''.__class__`) refusées par le bac à sable.

## Décisions et mesures du spike

| Sujet | Résultat |
| --- | --- |
| Bibliothèque de remplissage | `secretary` écartée : incompatible avec Jinja2 ≥ 3.1 et échoue sur les champs fragmentés. Moteur maison (~300 lignes, testé). |
| Conversion PDF | `soffice --headless --convert-to pdf` : ~0,9 s par document à chaud ; ~1,1 s tâche Celery + S3 de bout en bout. |
| UNO (processus LibreOffice persistant) | Écarté : image plus lourde (759 Mo, 2ᵉ interpréteur Python) pour un gain inutile à ce volume. |
| Image | ~800 Mo (`libreoffice-writer-nogui` + polices). |
| Concurrence | Un profil LibreOffice temporaire par conversion : 3 conversions simultanées OK. |
| Sécurité | Macros désactivées, délai maximal (groupe de processus tué), entrée vérifiée avant LibreOffice (qui convertirait sinon n'importe quel texte en PDF). |

## Configuration (variables d'environnement)

Aucun secret propre : le worker réutilise les secrets Kubernetes `millefeuille-s3` et `millefeuille-redis` ([`docs/secrets.md`](../../docs/secrets.md)). Il n'a ni jeton interne ni clé du LLM.

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `REDIS_URL` | URL Redis (avec mot de passe) : broker **et** résultats Celery. En Kubernetes, fournie par le secret `millefeuille-redis` | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Broker et résultats, **s'ils diffèrent** de `REDIS_URL` (docker-compose les définit) | `REDIS_URL` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET_NAME` | Accès au bucket : lit les modèles, écrit les documents et aperçus. Secret `millefeuille-s3` | `rustfsadmin`, `rustfsadmin`, `mille-feuille` |
| `AWS_ENDPOINT_URL` | Endpoint S3 (défini par le chart ; RustFS en docker-compose). Un hôte sans schéma reçoit `https://` | `http://localhost:9000` |
| `SOFFICE_BINARY` | Binaire LibreOffice | `soffice` |
| `SOFFICE_TIMEOUT_SECONDS` | Délai maximal d'une conversion ; au-delà, le processus est tué | `120` |
| `FC_MATCH_BINARY` | Binaire fontconfig, pour contrôler les polices d'un modèle à l'import | `fc-match` |

## Contrôle d'un modèle à l'import (`app/inspection.py`)

Un modèle peut être valide et produire pourtant un PDF différent de ce que voit son auteur. `inspect_template` relève, **sans rien bloquer** :

- les **polices** référencées par les styles du modèle et **absentes de l'image** (fontconfig, `fc-match`) : LibreOffice les remplace sans prévenir. Une police dont l'image a un équivalent de **mêmes métriques** (Arial → Liberation Sans, Times New Roman → Liberation Serif, Courier New → Liberation Mono, Calibri → Carlito, Cambria → Caladea) ne déclenche rien ;
- les **champs natifs LibreOffice** (champs utilisateur, variables, champs de saisie, texte conditionnel) : non remplis ;
- les **images** : conservées, mais une image variable (signature) n'est pas prise en charge.

Polices **installées dans l'image** : Liberation (Sans, Serif, Mono), Carlito, Caladea, DejaVu (Sans, Serif, Sans Mono), OpenSymbol. Pour en ajouter (par exemple **Marianne**, la police de l'État, si les modèles de la DDT l'utilisent) : ajouter le paquet ou copier les fichiers `.ttf` dans le `Dockerfile` (stage `runtime`), reconstruire l'image, puis rouvrir les modèles concernés : l'avertissement disparaît.

## Décisions (issue #148)

| Sujet | Décision |
| --- | --- |
| Placeholders dans un **cadre** (zone de texte), un **en-tête** ou un **pied de page** | Pris en charge (testé : champs trouvés et remplis). Les **boucles** `{%p`/`{%tr` dans un cadre ne sont pas testées. |
| **Champs natifs LibreOffice** | **Non pris en charge** : signalés à l'import, pas remplis. La syntaxe `{{ nom }}` est la seule. |
| **Images dynamiques** (signature, logo variable) | **Non pris en charge** pour l'instant, signalées à l'import. À reprendre si les modèles réels en ont besoin. |
| Police absente de l'image | Avertissement non bloquant ; on ajoute la police à l'image. |

## Déploiement

- **docker-compose** : service `worker-document-render` (file `document_render`).
- **Image** : construite par la CI (`ci.yml`, quand `worker/document_render/**` change) et publiée par le CD (`cd.yml`) sous `…-worker-document-render` ; versionnée par release-please avec les autres workers. Équivalent GitLab dans `.gitlab-ci-dso.yml` (build uniquement : lint et tests ne tournent que côté GitHub).
- **Helm** (`millefeuille/`) : composant `worker_render` (Deployment `millefeuille-worker-render`), configuré dans `values/common-values.yaml`. Il ne lit que les secrets `millefeuille-s3` (stockage) et `millefeuille-redis` (`REDIS_URL` : broker et résultats Celery), **pas** `millefeuille-worker` (jeton interne, clé du LLM) : il **n'appelle ni le backend ni le LLM**. Ressources adaptées à LibreOffice : 1 Gi demandé, **3 Gi** et 2 CPU en limite, pour deux conversions simultanées (`--concurrency=2`).
- **Mise à l'échelle** : `ScaledObject` KEDA `millefeuille-worker-render` sur la file Redis `document_render` (1 à 3 réplicas, seuil de 5 documents en attente).
- **Sécurité du pod** : le chart impose un utilisateur non-root, un système de fichiers racine en lecture seule et aucune capacité ; seul `/tmp` est inscriptible (emptyDir monté par le chart). L'image **convertit dans ces conditions** (vérifié avec `docker run --read-only --tmpfs /tmp --user 1000 --cap-drop ALL`) : le profil LibreOffice est créé dans un dossier temporaire par conversion.
- **Ordre de déploiement** : le backend appelle la tâche `inspect_template` : déployer le **worker avant (ou avec) le backend**, sinon l'import d'un modèle attend la fin du délai (30 s) puis répond « worker ne répond pas ».

## Limites connues

- **Fidélité** : celle des polices de l'image ; elle n'a pu être vérifiée qu'avec des modèles de test, **pas avec les vrais modèles de la DDT** (non disponibles). Procédure à suivre quand ils le seront : les importer (les avertissements disent quelles polices manquent), comparer le PDF au rendu de l'auteur, ajouter les polices manquantes à l'image.
- Seuls `content.xml` et `styles.xml` sont rendus : pas de champ dans les métadonnées du fichier.
- Boucles dans un cadre ou une zone de texte : non testées.

## Développement

```bash
cd worker/document_render
uv sync --group dev
uv run pytest                 # les tests marqués `libreoffice` sont ignorés sans soffice (la CI les exécute)
```

Tests avec LibreOffice réel, dans l'image :

```bash
docker build -t dd-render worker/document_render
docker run --rm -v "$PWD/worker/document_render":/src:ro -e HOME=/tmp --entrypoint sh dd-render -c \
  'cp -r /src /tmp/w && cd /tmp/w && rm -rf .venv && pip install -q --target /tmp/pt pytest && \
   PYTHONPATH=/tmp/pt:/tmp/w /app/.venv/bin/python -m pytest -q -p no:cacheprovider'
```
