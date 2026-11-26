import { ref } from "vue";

import type { AnalyseTheme } from "@/types/theme";
import { apiFetch } from "@/utils/api";

function mapVersion(api: any) {
  return { id: api.id, content: api.content as string, createdAt: api.created_at as string };
}

function mapTheme(api: any): AnalyseTheme {
  return {
    id: api.id,
    name: api.name,
    description: api.description,
    analyseCount: api.analyse_count,
    nameVersions: api.name_versions.map(mapVersion),
    descriptionVersions: api.description_versions.map(mapVersion),
  };
}

const themes = ref<AnalyseTheme[]>([]);
const unthemedCount = ref(0);
let lastRequest = 0;

export function useAnalyseThemes() {
  /** Les compteurs portent sur la recherche `q` quand il y en a une. */
  async function fetchThemes(q = "") {
    const request = ++lastRequest;
    const data = await apiFetch<any>(`/api/analyse-themes${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    // Une réponse dépassée par une recherche plus récente ne doit pas l'écraser.
    if (request !== lastRequest) return;
    themes.value = data.items.map(mapTheme);
    unthemedCount.value = data.unthemed_count;
  }

  function replace(api: any) {
    const theme = mapTheme(api);
    const index = themes.value.findIndex((t) => t.id === theme.id);
    if (index === -1) themes.value.push(theme);
    else themes.value[index] = theme;
    return theme;
  }

  async function createTheme(name: string, description: string) {
    const body = JSON.stringify({ name, description });
    return replace(await apiFetch<any>("/api/analyse-themes", { method: "POST", body }));
  }

  async function updateTheme(id: string, name: string, description: string) {
    const body = JSON.stringify({ name, description });
    return replace(await apiFetch<any>(`/api/analyse-themes/${id}`, { method: "PUT", body }));
  }

  async function restoreThemeVersion(id: string, versionId: string) {
    return replace(await apiFetch<any>(`/api/analyse-themes/${id}/versions/${versionId}/restore`, { method: "POST" }));
  }

  /** Les analyses du thème supprimé sont conservées : elles repassent « Sans thème ». */
  async function deleteTheme(id: string) {
    await apiFetch(`/api/analyse-themes/${id}`, { method: "DELETE" });
    themes.value = themes.value.filter((t) => t.id !== id);
  }

  return { themes, unthemedCount, fetchThemes, createTheme, updateTheme, restoreThemeVersion, deleteTheme };
}
