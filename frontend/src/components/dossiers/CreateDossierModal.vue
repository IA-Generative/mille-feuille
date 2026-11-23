<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";

import AppModal from "@/components/AppModal.vue";
import GroupPicker from "@/components/access/GroupPicker.vue";
import DocumentFileList from "@/components/dossiers/DocumentFileList.vue";
import SourcePicker from "@/components/dossiers/SourcePicker.vue";
import { fetchAnalyseSources, resolveSourceChoice } from "@/composables/useDocumentSources";
import { useAnalyses } from "@/composables/useAnalyses";
import { useDossierAccess } from "@/composables/useDossierAccess";
import { useDossiers } from "@/composables/useDossiers";
import { NO_SOURCE, type DocumentSource, type SourceChoice } from "@/types/documentSource";

const opened = defineModel<boolean>("opened", { default: false });
const emit = defineEmits<{ created: [] }>();

const { list: analyses, fetchList: fetchAnalyses } = useAnalyses();
const { create, addDocuments } = useDossiers();
const { myGroups } = useDossierAccess();

// Un nouveau dossier est restreint par défaut (#177) ; il faut au moins un des groupes de l'utilisateur, sinon le
// créateur lui-même ne pourrait plus l'ouvrir (le serveur le refuse aussi).
const restricted = ref(true);
const accessGroups = ref<string[]>([]);
const accessInvalid = computed(() => restricted.value && accessGroups.value.length === 0);

const analyseOptions = computed(() => analyses.value.map((analyse) => ({ value: analyse.id, text: analyse.name })));

const name = ref("");
const analyseId = ref<string | undefined>(undefined);
const aRanger = ref(false);
const files = ref<File[]>([]);
// Source des fichiers : celles de l'analyse choisie ; un dossier « à ranger » n'en a pas encore (on peut en créer une).
const sources = ref<DocumentSource[]>([]);
const sourceChoice = ref<SourceChoice>(NO_SOURCE);

// Ids qui relient chaque titre de section à son groupe (aria-labelledby), et ids des champs de la section Documents.
const infoTitleId = useId();
const accessTitleId = useId();
const docsTitleId = useId();
const fileUploadId = useId();
const sourceId = useId();

watch(opened, async (isOpened) => {
  if (isOpened) {
    name.value = "";
    files.value = [];
    sourceChoice.value = NO_SOURCE;
    aRanger.value = false;
    restricted.value = true;
    accessGroups.value = myGroups.value.length === 1 ? [...myGroups.value] : [];
    // La liste par défaut (useAnalyses) est paginée pour l'affichage ;
    // ce select doit lister toutes les analyses disponibles, donc on
    // recharge avec la taille de page maximale plutôt que de dépendre de
    // la page actuellement affichée sur AnalysesPage.
    await fetchAnalyses(1, 100);
    analyseId.value = analyses.value[0]?.id;
  }
});

watch([analyseId, aRanger], async () => {
  sourceChoice.value = NO_SOURCE;
  sources.value = !aRanger.value && analyseId.value ? await fetchAnalyseSources(analyseId.value).catch(() => []) : [];
});

function onFilesSelected(fileList: FileList) {
  files.value.push(...Array.from(fileList));
}

async function submit() {
  if (!name.value.trim()) return;
  if (!aRanger.value && !analyseId.value) return;
  if (accessInvalid.value) return;
  const dossier = await create(name.value.trim(), aRanger.value ? undefined : analyseId.value, {
    restricted: restricted.value,
    groups: accessGroups.value,
  });
  if (files.value.length > 0) {
    const sourceId = await resolveSourceChoice(dossier.id, sourceChoice.value);
    await addDocuments(dossier.id, files.value, sourceId);
  }
  opened.value = false;
  emit("created");
}
</script>

<template>
  <AppModal
    :opened="opened"
    @close="opened = false"
    title="Créer un dossier"
    size="lg"
    :actions="[
      { label: 'Annuler', secondary: true, onClick: () => (opened = false) },
      { label: 'Créer', onClick: submit, disabled: !name.trim() || (!aRanger && !analyseId) || accessInvalid },
    ]"
  >
    <p class="fr-text--sm fr-mb-3w">
      Les champs marqués d'un astérisque (<span class="fr-text--bold">*</span>) sont obligatoires.
    </p>

    <!-- Section 1 : quel dossier ? -->
    <div role="group" :aria-labelledby="infoTitleId" class="fr-mb-4w">
      <h2 :id="infoTitleId" class="fr-h6 fr-mb-2w">Informations du dossier</h2>

      <div class="fr-mb-2w">
        <DsfrInput v-model="name" label="Nom du dossier" label-visible required />
      </div>
      <div class="fr-mb-2w">
        <DsfrToggleSwitch
          v-model="aRanger"
          label="Dossier à ranger (sans analyse)"
          hint="Crée le dossier sans analyse rattachée. Des suggestions d'analyse seront générées automatiquement à partir des résumés des documents."
        />
      </div>

      <div v-if="!aRanger">
        <DsfrSelect v-model="analyseId" label="Analyse" required :options="analyseOptions" />
      </div>
    </div>

    <!-- Section 2 : qui peut le voir ? -->
    <div role="group" :aria-labelledby="accessTitleId" class="fr-mb-4w">
      <h2 :id="accessTitleId" class="fr-h6 fr-mb-2w">Accès</h2>

      <div class="fr-mb-2w">
        <DsfrToggleSwitch
          v-model="restricted"
          label="Dossier restreint"
          :hint="
            restricted
              ? 'Seuls les groupes choisis et les administrateurs voient ce dossier.'
              : 'Toute personne ayant accès à l\'analyse voit ce dossier.'
          "
        />
      </div>
      <GroupPicker
        v-if="restricted"
        v-model="accessGroups"
        :options="myGroups"
        legend="Groupes ayant accès"
        hint="Au moins un groupe, parmi les vôtres."
        required
        :error="accessInvalid ? 'Choisissez au moins un groupe.' : null"
      />
    </div>

    <!-- Section 3 : quels documents ? -->
    <div role="group" :aria-labelledby="docsTitleId">
      <h2 :id="docsTitleId" class="fr-h6 fr-mb-2w">Documents (facultatif)</h2>

      <DsfrFileUpload
        :id="fileUploadId"
        label="Documents et images du dossier"
        hint="PDF, JPG ou PNG."
        accept=".pdf,image/*"
        multiple
        @change="onFilesSelected"
      />

      <DocumentFileList :files="files" @remove="files.splice($event, 1)" />

      <div v-if="files.length > 0" class="fr-mt-3w">
        <SourcePicker v-model="sourceChoice" :sources="sources" :id="sourceId" />
      </div>
    </div>
  </AppModal>
</template>
