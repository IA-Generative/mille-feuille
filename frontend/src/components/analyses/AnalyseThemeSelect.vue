<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import VersionHistory from "@/components/analyses/VersionHistory.vue";
import { useAnalyses } from "@/composables/useAnalyses";
import { useAnalyseThemes } from "@/composables/useAnalyseThemes";
import type { Analyse, ThemeRef } from "@/types/analyse";
import { userMessage } from "@/utils/api";

const props = defineProps<{ analyse: Analyse; editable: boolean }>();

const { setTheme, restoreThemeAssignment } = useAnalyses();
const { themes, fetchThemes } = useAnalyseThemes();

const error = ref("");
const themeName = computed(() => themes.value.find((t) => t.id === props.analyse.themeId)?.name ?? "Sans thème");

async function attempt(action: () => Promise<unknown>) {
  error.value = "";
  try {
    await action();
  } catch (cause) {
    error.value = userMessage(cause, "Le thème n'a pas pu être changé.");
  }
}

function choose(event: Event) {
  const select = event.target as HTMLSelectElement;
  attempt(() => setTheme(props.analyse.id, select.value || null)).then(() => {
    // En cas d'échec, le sélecteur doit revenir au thème réel.
    select.value = props.analyse.themeId ?? "";
  });
}

const formatTheme = (content: ThemeRef) => content.name ?? "Sans thème";

onMounted(() => attempt(() => fetchThemes()));
</script>

<template>
  <div class="analyse-theme">
    <div class="analyse-theme__row">
      <template v-if="editable">
        <label class="analyse-theme__label" :for="`theme-${analyse.id}`">Thème</label>
        <select :id="`theme-${analyse.id}`" class="fr-select analyse-theme__select" :value="analyse.themeId ?? ''" @change="choose">
          <option value="">Sans thème</option>
          <option v-for="theme in themes" :key="theme.id" :value="theme.id">{{ theme.name }}</option>
        </select>
      </template>
      <!-- Sans le droit de modifier l'analyse : le thème reste visible. -->
      <span v-else class="analyse-theme__label">Thème : {{ themeName }}</span>
    </div>
    <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
    <VersionHistory
      v-if="editable"
      :versions="analyse.themeVersions"
      :format-content="formatTheme"
      @restore="(versionId: string) => attempt(() => restoreThemeAssignment(analyse.id, versionId))"
    />
  </div>
</template>

<style scoped>
.analyse-theme__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.analyse-theme__label {
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.analyse-theme__select {
  width: auto;
  min-width: 14rem;
  margin: 0;
  font-size: 0.875rem;
}
</style>
