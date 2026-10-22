/** Minuscules sans accents : « Légifrance » est trouvé par « legifrance ». */
export function normalizeSearch(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/** Vrai si `haystack` contient la recherche (une recherche vide correspond à tout). */
export function matchesSearch(query: string, haystack: string): boolean {
  const needle = normalizeSearch(query.trim());
  return needle === "" || normalizeSearch(haystack).includes(needle);
}
