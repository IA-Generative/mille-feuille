<script setup lang="ts">
import { computed, ref, watch } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import ModelPicker from "@/components/ModelPicker.vue";
import type { Version } from "@/types/analyse";
import type { ChunkStrategy, EmbeddingModel, SearchImpact, SearchSettings } from "@/types/search";

// Réglages de recherche d'une analyse : comment les pages sont découpées en passages, et avec quel modèle elles sont
// vectorisées. Versionné avec historique et restauration. Le composant ne fait aucun appel : il émet `save`, `restore`
// et `change` (pour que le parent calcule l'impact avant l'enregistrement).
const props = defineProps<{
  settings: SearchSettings;
  versions: Version<SearchSettings>[];
  embeddingModels: EmbeddingModel[];
  impact: SearchImpact | null;
  saving?: boolean;
}>();
const emit = defineEmits<{
  save: [settings: SearchSettings];
  restore: [versionId: string];
  change: [settings: SearchSettings];
}>();

const strategy = ref<ChunkStrategy>(props.settings.strategy);
const chunkModel = ref(props.settings.chunkModel ?? "");
const embeddingModel = ref(props.settings.embeddingModel ?? "");
const size = ref<number | string>(props.settings.size);
const overlap = ref<number | string>(props.settings.overlap);
const window = ref<number | string>(props.settings.window);

watch(
  () => props.settings,
  (s) => {
    strategy.value = s.strategy;
    chunkModel.value = s.chunkModel ?? "";
    embeddingModel.value = s.embeddingModel ?? "";
    size.value = s.size;
    overlap.value = s.overlap;
    window.value = s.window;
  },
);

const current = computed<SearchSettings>(() => ({
  strategy: strategy.value,
  chunkModel: chunkModel.value || null,
  size: Number(size.value),
  overlap: Number(overlap.value),
  window: Number(window.value),
  embeddingModel: embeddingModel.value || null,
}));

const signature = (s: SearchSettings) => JSON.stringify(s);
const isDirty = computed(() => signature(current.value) !== signature(props.settings));

const errors = computed(() => {
  const list: string[] = [];
  const s = current.value;
  if (!Number.isInteger(s.size) || s.size < 100 || s.size > 10000) list.push("La taille d'un passage est comprise entre 100 et 10 000 caractères.");
  else if (!Number.isInteger(s.overlap) || s.overlap < 0 || s.overlap >= s.size) list.push("Le chevauchement est positif et plus petit que la taille d'un passage.");
  if (!Number.isInteger(s.window) || s.window < 0 || s.window > 5) list.push("La fenêtre est comprise entre 0 et 5 passages.");
  return list;
});

// L'impact se calcule dès qu'on change un réglage valide, avant tout enregistrement.
watch(current, (s) => {
  if (isDirty.value && !errors.value.length) emit("change", s);
});

const embeddingOptions = computed(() => [
  { value: "", text: "Modèle par défaut de la plateforme" },
  ...props.embeddingModels.map((m) => ({ value: m.id, text: `${m.id} (${m.dimension} dimensions)` })),
]);

function save() {
  if (errors.value.length || !isDirty.value) return;
  emit("save", current.value);
}

function formatVersion(s: SearchSettings) {
  const chunking = s.strategy === "ia" ? `découpage par IA${s.chunkModel ? ` (${s.chunkModel})` : ""}` : `découpage classique ${s.size}/${s.overlap}`;
  return `${chunking} · embeddings : ${s.embeddingModel ?? "modèle par défaut"} · fenêtre ${s.window}`;
}

const impactText = computed(() => {
  const i = props.impact;
  if (!i || !isDirty.value) return "";
  if (i.problem) return i.problem;
  if (!i.changesIndex) return "Ce changement ne demande aucune reconstruction.";
  if (i.obsoleteDossiers === 0) return "Aucun dossier n'est encore indexé : rien à reconstruire.";
  const dossiers = i.obsoleteDossiers === 1 ? "1 dossier indexé sera à reconstruire" : `${i.obsoleteDossiers} dossiers indexés seront à reconstruire`;
  return `${dossiers}${i.usesAiChunking ? ", avec un appel au modèle de découpage pour chaque page" : ""}. Ils gardent leur index actuel jusqu'à la reconstruction.`;
});
</script>

<template>
  <div class="ssf">
    <h4 class="fr-h6 ssf__title">Recherche dans les dossiers</h4>
    <p class="fr-text--sm ssf__intro">
      Les pages d'un dossier sont découpées en passages, puis vectorisées pour que le chat et les agents retrouvent les bons extraits,
      même quand les mots diffèrent.
    </p>

    <fieldset class="fr-fieldset ssf__strategy" aria-label="Découpage des pages">
      <legend class="fr-fieldset__legend fr-text--bold">Découpage des pages</legend>
      <div class="fr-fieldset__element">
        <div class="fr-radio-group">
          <input id="ssf-ia" v-model="strategy" type="radio" name="ssf-strategy" value="ia" />
          <label class="fr-label" for="ssf-ia">
            Par un modèle d'IA
            <span class="fr-hint-text">Coupe aux frontières de sens : un paragraphe, une clause, une rubrique de formulaire.</span>
          </label>
        </div>
      </div>
      <div class="fr-fieldset__element">
        <div class="fr-radio-group">
          <input id="ssf-classique" v-model="strategy" type="radio" name="ssf-strategy" value="classique" />
          <label class="fr-label" for="ssf-classique">
            Classique
            <span class="fr-hint-text">Passages de taille fixe, qui se chevauchent. Rapide et sans modèle.</span>
          </label>
        </div>
      </div>
    </fieldset>

    <div v-if="strategy === 'ia'" class="ssf__field">
      <ModelPicker v-model="chunkModel" label="Modèle de découpage" show-label block />
    </div>

    <div v-else class="ssf__numbers">
      <div>
        <label class="fr-label" for="ssf-size">Taille d'un passage<span class="fr-hint-text">En caractères</span></label>
        <input id="ssf-size" v-model="size" type="number" min="100" max="10000" class="fr-input" />
      </div>
      <div>
        <label class="fr-label" for="ssf-overlap">Chevauchement<span class="fr-hint-text">En caractères</span></label>
        <input id="ssf-overlap" v-model="overlap" type="number" min="0" class="fr-input" />
      </div>
    </div>

    <div class="ssf__field ssf__window">
      <label class="fr-label" for="ssf-window">
        Passages voisins renvoyés
        <span class="fr-hint-text">De chaque côté du passage trouvé, pour donner du contexte. 0 : le passage seul.</span>
      </label>
      <input id="ssf-window" v-model="window" type="number" min="0" max="5" class="fr-input" />
    </div>

    <div class="ssf__field">
      <label class="fr-label" for="ssf-embedding">
        Modèle d'embeddings
        <span class="fr-hint-text">Le même modèle sert à indexer les passages et à comprendre les questions.</span>
      </label>
      <select id="ssf-embedding" v-model="embeddingModel" class="fr-select">
        <option v-for="option in embeddingOptions" :key="option.value" :value="option.value">{{ option.text }}</option>
      </select>
    </div>

    <ul v-if="errors.length" class="ssf__errors" role="alert">
      <li v-for="message in errors" :key="message">{{ message }}</li>
    </ul>
    <p v-if="impactText" class="fr-text--sm ssf__impact" role="status" aria-live="polite">{{ impactText }}</p>

    <DsfrButton label="Enregistrer" :disabled="!isDirty || errors.length > 0 || saving" @click="save" />

    <VersionHistory :versions="versions" :format-content="formatVersion" @restore="emit('restore', $event)" />
  </div>
</template>

<style scoped>
.ssf__title,
.ssf__intro {
  margin: 0 0 0.75rem;
}

.ssf__intro {
  color: var(--text-mention-grey);
}

.ssf__strategy {
  margin: 1rem 0;
}

.ssf__field {
  margin: 1rem 0;
  max-width: 28rem;
}

.ssf__numbers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 14rem));
  gap: 1rem;
  margin: 1rem 0;
}

.ssf__window .fr-input {
  max-width: 8rem;
}

.ssf__errors {
  margin: 0 0 1rem;
  padding-left: 1.25rem;
  color: var(--text-default-error);
}

.ssf__impact {
  margin: 0 0 1rem;
  color: var(--text-mention-grey);
}
</style>
