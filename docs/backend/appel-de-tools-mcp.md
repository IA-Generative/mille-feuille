# Appeler un tool MCP : le proxy du backend

Issue [#338](https://github.com/IA-Generative/mille-feuille/issues/338), dans l'épique [#343](https://github.com/IA-Generative/mille-feuille/issues/343). **Le worker demande « appelle ce tool » et ne reçoit que le résultat : aucun jeton ne passe par lui.**

## La route

`POST /api/internal/tools/{tool_id}/call`, avec le jeton du worker (`X-App-Token`) et la personne pour qui l'agent travaille (`X-Acting-User`).

```json
// requête
{ "arguments": { "mots_cles": "subvention association" }, "run_id": "run-42" }

// réponse (toujours 200 : une erreur métier n'est pas une erreur HTTP)
{ "ok": true, "code": null, "output": "Article L1111-1 : …", "truncated": false, "untrusted": true, "duration_ms": 412 }
```

`tool_id` est l'identifiant d'un tool MCP (voir `GET /api/tool-servers`). Un tool **interne** n'est pas appelé ici : il est exécuté par le worker (réponse `outil_interne`).

## Ce que le proxy fait, dans l'ordre

1. résout le tool ; un serveur que la personne ne voit pas répond **`outil_inconnu`**, comme s'il n'existait pas ;
2. refuse un tool non autorisé (`outil_desactive`) et des arguments trop volumineux (`arguments_trop_longs`) ;
3. applique les **quotas** : appels par run (`TOOL_CALLS_PER_RUN`) et par personne et par minute (`TOOL_CALLS_PER_MINUTE`), sinon `quota_depasse` ;
4. **revérifie l'adresse du serveur** à chaque appel (`adresse_refusee`) : une adresse qui change entre l'ajout et l'appel ne passe pas ;
5. obtient le **jeton de la personne** par échange Keycloak (voir [echange-de-jeton-mcp.md](echange-de-jeton-mcp.md)) ;
6. appelle le tool (délai `TOOL_CALL_TIMEOUT_SECONDS`) ;
7. **borne la sortie** (`TOOL_OUTPUT_MAX_CHARS`) et la marque `untrusted` ;
8. **journalise** l'appel.

## Les codes d'échec

Chaque code est stable et accompagné d'un message en français, lisible par le modèle (dans `output`).

| Code | Cause |
| --- | --- |
| `outil_interne`, `outil_inconnu`, `outil_desactive` | le tool n'est pas appelable ici |
| `arguments_trop_longs`, `quota_depasse` | limites |
| `adresse_refusee` | l'adresse du serveur n'est plus autorisée |
| `session_requise`, `echange_refuse`, `audience_manquante`, `identite_absente` | identité (voir l'échange de jeton) |
| `delai_depasse`, `serveur_indisponible` | le serveur ne répond pas |
| `outil_en_erreur` | le tool a répondu par une erreur ; sa sortie est dans `output` |

## Le contenu d'un serveur tiers n'est pas une consigne

`untrusted` est toujours vrai : la sortie vient d'un serveur que n'importe quel utilisateur a pu ajouter. Le worker (issue #340) la présente au modèle comme **donnée à ne pas suivre**, jamais comme instruction.

## Le journal

Table `tool_call_logs` : personne, serveur (nom conservé si le serveur est supprimé), tool, run, durée, issue (`ok` ou le code). **Ni les arguments ni la sortie** : ils peuvent contenir des données personnelles.

## Les modules

| Module | Rôle |
| --- | --- |
| `routers/internal_tools.py` | la route |
| `services/tools/call_service.py` | l'orchestration, de bout en bout |
| `services/tools/mcp_caller.py` | le client MCP (`tools/call`), derrière une interface |
| `services/tools/call_limits.py` | les quotas (Redis) |
| `services/tools/call_result.py` | le résultat, les messages, la borne de taille |
| `repositories/tool_call_log_repository.py` | le journal |
