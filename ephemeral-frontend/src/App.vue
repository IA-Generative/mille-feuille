<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import DefinitionList from "@/components/DefinitionList.vue";
import FileDropzone from "@/components/FileDropzone.vue";
import AppFooter from "@/components/AppFooter.vue";
import ApiDocs from "@/components/ApiDocs.vue";
import ChangelogView from "@/components/ChangelogView.vue";
import TaskList from "@/components/TaskList.vue";
import ResultView from "@/components/ResultView.vue";
import { MILLEFEUILLE_URL } from "@/config";
import { useAuth } from "@/composables/useAuth";
import { useEphemeralRun } from "@/composables/useEphemeralRun";
import { TERMINAL, type EntityDef, type LabelDef, type Mode } from "@/types";

const millefeuilleUrl = MILLEFEUILLE_URL;
const { email, checked, fetchProfile, login, logout } = useAuth();
const run = useEphemeralRun();

const mode = ref<Mode>("classification");
const file = ref<File | null>(null);
const labels = ref<LabelDef[]>([{ name: "", definition: "" }]);
const entities = ref<EntityDef[]>([{ name: "", definition: "", type: "texte" }]);
const multiLabel = ref(false);
const prompt = ref("");
const ttlHours = ref(24);
const persist = ref(false);
const showOptions = ref(false);
const view = ref<"new" | "tasks" | "docs" | "changelog">("new");

const definitionsReady = computed(() =>
  (mode.value === "classification" ? labels.value : entities.value).some((row) => row.name.trim()),
);
const canSubmit = computed(() => !!file.value && definitionsReady.value && !run.submitting.value);
const running = computed(() => !!run.runId.value && !!run.result.value && !TERMINAL.includes(run.result.value.status));

const submit = () => {
  if (!file.value) return;
  const clean = <T extends { name: string }>(rows: T[]) => rows.filter((row) => row.name.trim());
  run.start({
    mode: mode.value,
    file: file.value,
    ttlHours: ttlHours.value,
    persist: persist.value,
    prompt: prompt.value,
    multiLabel: multiLabel.value,
    labels: clean(labels.value),
    entities: clean(entities.value),
  });
};

// Le run reste dans « Mes tâches » (jusqu'à son TTL, ou indéfiniment s'il est conservé) : on ne le supprime pas.
const reset = () => {
  run.close();
  file.value = null;
  view.value = "new";
};

const openTask = async (id: string, kind: Mode) => {
  await run.open(id, kind);
  view.value = "new";
};

onMounted(fetchProfile);
</script>

<template>
  <header class="fr-header" role="banner">
    <div class="fr-container head">
      <p class="fr-h6 fr-m-0" title="Version restreinte de MilleFeuille : une seule feuille, un seul document à la fois">
        UneFeuille <span class="fr-badge fr-badge--sm fr-badge--blue-ecume">Version restreinte</span>
      </p>
      <a v-if="millefeuilleUrl" class="fr-link fr-icon-arrow-right-line fr-link--icon-right" :href="millefeuilleUrl">
        Accéder à MilleFeuille
      </a>
      <div v-if="checked">
        <template v-if="email">
          <span class="fr-text--sm fr-mr-2w">{{ email }}</span>
          <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="logout">Se déconnecter</button>
        </template>
        <button v-else class="fr-btn fr-btn--sm" @click="login">Se connecter</button>
      </div>
    </div>
  </header>

  <main class="fr-container narrow fr-py-6w">
    <h1 class="fr-h2">Classez ou extrayez un document</h1>
    <p class="fr-text--lead">
      Déposez un document, dites ce que vous cherchez, récupérez le résultat. Par défaut, le fichier est supprimé dès la
      fin du traitement et le résultat purgé après {{ ttlHours }} h. Cochez « Conserver » pour tout garder.
    </p>

    <nav class="fr-mb-3w" aria-label="Sections">
      <ul class="fr-btns-group fr-btns-group--inline fr-btns-group--sm">
        <li><button class="fr-btn" :class="{ 'fr-btn--tertiary': view !== 'new' }" @click="view = 'new'; run.close()">Nouveau</button></li>
        <li><button class="fr-btn" :class="{ 'fr-btn--tertiary': view !== 'tasks' }" @click="view = 'tasks'">Mes tâches</button></li>
        <li><button class="fr-btn" :class="{ 'fr-btn--tertiary': view !== 'docs' }" @click="view = 'docs'">API</button></li>
      </ul>
    </nav>

    <ApiDocs v-if="view === 'docs'" />
    <ChangelogView v-else-if="view === 'changelog'" />

    <div v-else-if="checked && !email" class="fr-callout">
      <p class="fr-callout__text">Connectez-vous pour utiliser le service.</p>
      <button class="fr-btn" @click="login">Se connecter</button>
    </div>

    <template v-else-if="email">
      <TaskList v-if="view === 'tasks'" @open="openTask" />

      <section v-else-if="!run.runId.value">
        <div class="fr-segmented fr-mb-3w">
          <div class="fr-segmented__elements">
            <div v-for="m in ['classification', 'extraction'] as Mode[]" :key="m" class="fr-segmented__element">
              <input :id="`mode-${m}`" v-model="mode" type="radio" name="mode" :value="m" />
              <label class="fr-label" :for="`mode-${m}`">{{ m === "classification" ? "Classification" : "Extraction" }}</label>
            </div>
          </div>
        </div>

        <FileDropzone v-model="file" />

        <h2 class="fr-h5 fr-mt-4w">{{ mode === "classification" ? "Catégories" : "Informations à extraire" }}</h2>
        <DefinitionList
          v-if="mode === 'classification'"
          v-model="labels"
          add-label="Ajouter une catégorie"
          name-placeholder="Nom (ex. CNI)"
        />
        <DefinitionList
          v-else
          v-model="entities"
          with-type
          add-label="Ajouter une information"
          name-placeholder="Nom (ex. date de naissance)"
        />

        <button type="button" class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-mt-3w" @click="showOptions = !showOptions">
          {{ showOptions ? "Masquer" : "Afficher" }} les options
        </button>
        <div v-if="showOptions" class="fr-mt-2w options">
          <div v-if="mode === 'classification'" class="fr-checkbox-group">
            <input id="multi" v-model="multiLabel" type="checkbox" />
            <label class="fr-label" for="multi">Plusieurs catégories possibles par page</label>
          </div>
          <div class="fr-input-group">
            <label class="fr-label" for="prompt">Consigne complémentaire (facultatif)</label>
            <textarea id="prompt" v-model="prompt" class="fr-input" rows="2"></textarea>
          </div>
          <div class="fr-checkbox-group fr-mb-2w">
            <input id="persist" v-model="persist" type="checkbox" />
            <label class="fr-label" for="persist">
              Conserver le document et le résultat
              <span class="fr-hint-text">Sinon, le fichier est supprimé à la fin et le résultat après la durée ci-dessous.</span>
            </label>
          </div>
          <div v-if="!persist" class="fr-input-group">
            <label class="fr-label" for="ttl">Conservation du résultat (heures, 1 à 17 520)</label>
            <input id="ttl" v-model.number="ttlHours" class="fr-input" type="number" min="1" max="17520" />
          </div>
        </div>

        <p v-if="run.error.value" class="fr-error-text fr-mt-2w">{{ run.error.value }}</p>
        <button class="fr-btn fr-btn--lg fr-mt-4w" :disabled="!canSubmit" @click="submit">
          {{ run.submitting.value ? "Envoi…" : mode === "classification" ? "Classer le document" : "Extraire les informations" }}
        </button>
      </section>

      <section v-else>
        <div class="bar fr-mb-3w">
          <p class="fr-m-0">
            <span class="fr-badge" :class="running || !run.result.value ? 'fr-badge--info' : run.result.value.status === 'terminé' ? 'fr-badge--success' : 'fr-badge--error'">
              {{ run.result.value?.status ?? "en_attente" }}
            </span>
          </p>
          <div class="actions">
            <button v-if="running" class="fr-btn fr-btn--secondary fr-btn--sm" @click="run.stop">Arrêter</button>
            <button class="fr-btn fr-btn--tertiary fr-btn--sm" @click="reset">Nouveau document</button>
          </div>
        </div>
        <p v-if="running || !run.result.value" class="fr-text--sm" aria-live="polite">Traitement en cours…</p>
        <p v-if="run.error.value" class="fr-error-text">{{ run.error.value }}</p>
        <p v-if="run.result.value?.error" class="fr-error-text">{{ run.result.value.error }}</p>
        <ResultView v-if="run.result.value" :result="run.result.value" :mode="run.mode.value" />
        <p v-if="run.result.value?.expires_at" class="fr-text--xs">
          Résultat supprimé le {{ new Date(run.result.value.expires_at).toLocaleString("fr-FR") }}.
        </p>
      </section>
    </template>
  </main>

  <AppFooter @changelog="view = 'changelog'" @docs="view = 'docs'" />
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-block: 1rem;
}
.narrow {
  max-width: 48rem;
}
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
</style>
