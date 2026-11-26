import type { Version } from "@/types/analyse";

/** Un thème range des analyses (une analyse appartient à un thème au plus). */
export interface AnalyseTheme {
  id: string;
  name: string;
  description: string;
  analyseCount: number;
  nameVersions: Version<string>[];
  descriptionVersions: Version<string>[];
}
