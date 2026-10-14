<script setup lang="ts">
/**
 * Bandeau de relance de l'analyse d'un dossier : proposé quand la dernière exécution a échoué, ou quand l'analyse
 * a été mise à jour depuis le dernier lancement. Une relance crée une nouvelle analyse de dossier qui ne recalcule
 * que ce qui a changé et reprend le reste (voir docs/backend/relance-incrementale.md). Proposé aussi quand des
 * fichiers ont été ajoutés depuis le dernier lancement (jamais refusés : on prévient qu'il faut relancer).
 */
import { computed } from "vue";

const props = defineProps<{
  /** La dernière exécution du dossier est en échec. */
  failed: boolean;
  /** Version de l'analyse utilisée au dernier lancement, et version courante de l'analyse. */
  launchedVersion: string;
  currentVersion?: string;
  busy?: boolean;
  /** Fichiers ajoutés depuis le dernier lancement, pas encore pris en compte. */
  newDocuments?: number;
  /** Une exécution est en cours : on prévient, mais la relance n'est possible qu'à sa fin. */
  running?: boolean;
}>();

const emit = defineEmits<{ relaunch: [] }>();

const outdated = computed(() => !!props.currentVersion && props.currentVersion !== props.launchedVersion);
const hasNewDocuments = computed(() => (props.newDocuments ?? 0) > 0);
const visible = computed(() => props.failed || outdated.value || hasNewDocuments.value);
</script>

<template>
  <div v-if="visible" class="relaunch" role="status">
    <VIcon :name="failed ? 'ri-error-warning-line' : 'ri-refresh-line'" class="relaunch__icon" />
    <div class="relaunch__text">
      <strong v-if="failed">L'analyse de ce dossier a échoué.</strong>
      <strong v-else-if="hasNewDocuments">
        {{ newDocuments === 1 ? "Un fichier a été ajouté" : `${newDocuments} fichiers ont été ajoutés` }} depuis le
        dernier lancement.
      </strong>
      <strong v-else>L'analyse a été mise à jour.</strong>
      <span v-if="hasNewDocuments" class="fr-text--sm relaunch__detail">
        {{ newDocuments === 1 ? "Il n'est" : "Ils ne sont" }} pas pris en compte : relancez l'analyse.
        <template v-if="running">La relance sera possible à la fin de l'exécution en cours.</template>
      </span>
      <span v-if="outdated" class="fr-text--sm relaunch__detail">
        Ce dossier a été traité avec la version {{ launchedVersion }} ; la version courante est la
        {{ currentVersion }}.
      </span>
      <span class="fr-text--sm relaunch__detail">
        Une relance ne recalcule que ce qui a changé et reprend le reste, y compris vos corrections.
      </span>
    </div>
    <DsfrButton
      :label="failed || hasNewDocuments ? 'Relancer l\'analyse' : 'Relancer avec la nouvelle version'"
      icon="ri-refresh-line"
      size="sm"
      :disabled="busy || running"
      @click="emit('relaunch')"
    />
  </div>
</template>

<style scoped>
.relaunch {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-left: 3px solid var(--border-action-high-blue-france);
  border-radius: 0.5rem;
  background: var(--background-default-grey);
}

.relaunch__icon {
  flex: 0 0 auto;
  color: var(--text-action-high-blue-france);
}

.relaunch__text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.relaunch__detail {
  margin: 0;
  color: var(--text-mention-grey);
}
</style>
