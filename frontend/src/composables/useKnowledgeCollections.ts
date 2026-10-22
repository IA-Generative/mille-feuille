import { computed, ref } from "vue";

import type { KnowledgeCollection } from "@/types/knowledge";
import type { Version } from "@/types/analyse";

// Données simulées (phase 1, docs/tools-mcp-plan.md) : les collections de la base de connaissances, et celles que
// l'analyse autorise. La sélection est sauvegardée par analyse, avec historique (règle « tout est versionné »).

const collection = (id: string, name: string, description: string, documentCount: number): KnowledgeCollection => ({
  id,
  name,
  description,
  documentCount,
});

const collections = ref<KnowledgeCollection[]>([
  collection("ceseda", "CESEDA : textes et commentaires", "Code de l'entrée et du séjour des étrangers et du droit d'asile.", 1240),
  collection("ce", "Jurisprudence du Conseil d'État", "Décisions du Conseil d'État depuis 1990.", 8410),
  collection("ta", "Jurisprudence des tribunaux administratifs", "Décisions des tribunaux administratifs.", 12030),
  collection("circulaires", "Circulaires et instructions ministérielles", "Circulaires publiées au Bulletin officiel.", 960),
  collection("subv-guide", "Guide de l'instruction des subventions", "Procédures et pièces à exiger pour une subvention.", 85),
  collection("courriers", "Modèles de courriers", "Courriers types de l'administration.", 140),
  collection("crpa", "Code des relations entre le public et l'administration", "Textes et commentaires du CRPA.", 420),
  collection("cgct", "Code général des collectivités territoriales", "Textes et commentaires du CGCT.", 2100),
  collection("secu-routiere", "Code de la sécurité routière", "Textes, barèmes et commentaires.", 760),
  collection("service-public", "Fiches pratiques Service-Public", "Fiches pratiques à destination des usagers.", 3500),
  collection("doctrine", "Doctrine interne", "Notes de doctrine des services.", 230),
  collection("reponses", "Réponses ministérielles", "Réponses aux questions parlementaires.", 5100),
]);

const daysAgo = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

const selectedIds = ref<string[]>(["subv-guide", "crpa", "circulaires"]);
const versions = ref<Version<string[]>[]>([
  { id: "kv-2", createdAt: daysAgo(6), content: ["subv-guide", "crpa"] },
  { id: "kv-1", createdAt: daysAgo(20), content: ["subv-guide"] },
]);

export function useKnowledgeCollections() {
  const selected = computed(() => collections.value.filter((c) => selectedIds.value.includes(c.id)));

  function save(ids: string[]) {
    versions.value = [{ id: `kv-${Date.now()}`, createdAt: new Date().toISOString(), content: [...selectedIds.value] }, ...versions.value];
    selectedIds.value = ids;
  }

  function restore(versionId: string) {
    const version = versions.value.find((v) => v.id === versionId);
    if (version) save([...version.content]);
  }

  const nameOf = (ids: string[]) =>
    ids.length > 0 ? ids.map((id) => collections.value.find((c) => c.id === id)?.name ?? id).join(", ") : "(aucune collection)";

  return { collections, selectedIds, selected, versions, save, restore, nameOf };
}
