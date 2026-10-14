<script setup lang="ts">
import { API_BASE_URL } from "@/api";

const base = API_BASE_URL || window.location.origin;

const classification = `curl -X POST "${base}/api/ephemeral/classifications?ttl_hours=24" \\
  -H "X-App-Token: $KEY" \\
  -F file=@dossier.pdf \\
  -F 'labels=[{"name":"CNI","definition":"Carte nationale d identité"},{"name":"RIB","definition":"Relevé d identité bancaire"}]' \\
  -F multi_label=false \\
  -F persist=false`;

const extraction = `curl -X POST "${base}/api/ephemeral/extractions?ttl_hours=24" \\
  -H "X-App-Token: $KEY" \\
  -F file=@facture.pdf \\
  -F 'entities=[{"name":"montant","definition":"Montant TTC","type":"nombre"},{"name":"date","definition":"Date de la facture","type":"date"}]'`;

const read = `curl "${base}/api/ephemeral/classifications/$RUN_ID" -H "X-App-Token: $KEY"
curl "${base}/api/ephemeral/extractions/$RUN_ID" -H "X-App-Token: $KEY"`;

const manage = `curl "${base}/api/ephemeral/runs" -H "X-App-Token: $KEY"                      # lister
curl -X POST   "${base}/api/ephemeral/runs/$RUN_ID/stop" -H "X-App-Token: $KEY"   # arrêter
curl -X DELETE "${base}/api/ephemeral/runs/$RUN_ID" -H "X-App-Token: $KEY"        # supprimer`;

const token = `curl -X POST "${base}/api/app-tokens" \\
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \\
  -d '{"name": "mon-integration"}'`;
</script>

<template>
  <div class="docs">
    <h2 class="fr-h4">Utiliser le service par API</h2>
    <p>
      Tout ce que fait cette page est disponible en HTTP. Un traitement est créé, puis lu avec son
      <code>run_id</code>. Référence complète : <a :href="`${base}/api/docs`" target="_blank" rel="noopener">Swagger</a>,
      rubrique « Ephemeral ».
    </p>

    <h3 class="fr-h6">1. Une clé d'API</h3>
    <p>
      Créez-la une fois avec <code>POST /api/app-tokens</code> (depuis Swagger, une fois connecté, ou avec un jeton de
      session). Elle n'est affichée qu'à la création. Envoyez-la ensuite dans l'en-tête <code>X-App-Token</code> (ou
      <code>Authorization: Bearer</code>) ; vous ne voyez que ce que vous avez créé.
    </p>
    <pre>{{ token }}</pre>

    <h3 class="fr-h6">2. Classer un document</h3>
    <p>
      <code>labels</code> : au moins une catégorie. <code>multi_label</code> : une ou plusieurs catégories par page.
      Chaque page reçoit deux classifications, <code>textual</code> (texte) et <code>visual</code> (apparence).
    </p>
    <pre>{{ classification }}</pre>

    <h3 class="fr-h6">3. Extraire des informations</h3>
    <p>
      <code>type</code> : texte, date, nombre, booléen ou identifiant. Deux extractions : <code>textual</code> (LLM) et
      <code>gliner</code>.
    </p>
    <pre>{{ extraction }}</pre>

    <h3 class="fr-h6">4. Lire le résultat</h3>
    <p>
      La réponse de création contient <code>run_id</code>. Interrogez-la jusqu'à ce que <code>status</code> soit
      <code>terminé</code> (ou <code>échec</code> / <code>arrêté</code>).
    </p>
    <pre>{{ read }}</pre>

    <h3 class="fr-h6">5. Gérer ses traitements</h3>
    <pre>{{ manage }}</pre>

    <h3 class="fr-h6">Conservation</h3>
    <ul>
      <li>
        Par défaut (<code>persist=false</code>), le fichier est supprimé à la fin du traitement et le résultat reste
        <code>ttl_hours</code> heures (24 par défaut, 17 520 au plus), puis il est purgé.
      </li>
      <li>
        <code>persist=true</code> garde le document et le résultat sans expiration. Réservé aux clés d'API de compte
        ; la clé d'environnement du service ne le permet pas.
      </li>
    </ul>
  </div>
</template>

<style scoped>
pre {
  overflow-x: auto;
  padding: 1rem;
  border-radius: 0.5rem;
  background: var(--background-alt-grey);
  font-size: 0.8125rem;
  line-height: 1.5;
}
</style>
