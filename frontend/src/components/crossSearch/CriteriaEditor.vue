<script setup lang="ts">
/** Ce que les dossiers doivent avoir en commun : des entités définies dans les analyses, ou le même fichier. */
import { computed, ref } from "vue";

import EquivalenceSuggestions from "@/components/crossSearch/EquivalenceSuggestions.vue";
import { analysesOf, ENTITY_CATALOG, similarToName } from "@/composables/mockEntityCatalog";
import { CRITERION_ORIGINS, type RuleCriterion } from "@/types/crossSearch";

const criteria = defineModel<RuleCriterion[]>({ required: true });

const analyses = [...new Set(ENTITY_CATALOG.map((e) => e.analyseName))].map((name) => ({
  name,
  entities: ENTITY_CATALOG.filter((e) => e.analyseName === name),
}));
const labelOf = (id: string) => ENTITY_CATALOG.find((e) => e.id === id)?.id ?? id;

const newId = () => `criterion-${Date.now()}-${criteria.value.length}`;
const add = (criterion: RuleCriterion) => (criteria.value = [...criteria.value, criterion]);
const remove = (id: string) => (criteria.value = criteria.value.filter((c) => c.id !== id));

function addFromAnalyses(event: Event) {
  const select = event.target as HTMLSelectElement;
  const entity = ENTITY_CATALOG.find((e) => e.id === select.value);
  if (entity) add({ id: newId(), origin: "analysis", name: entity.name, entityIds: [entity.id] });
  select.value = "";
}

function addEquivalent(criterion: RuleCriterion, event: Event) {
  const select = event.target as HTMLSelectElement;
  if (criterion.origin === "analysis" && select.value) criterion.entityIds = [...criterion.entityIds, select.value];
  select.value = "";
}

function accept(criterion: RuleCriterion, id: string) {
  if (criterion.origin === "analysis") criterion.entityIds = [...criterion.entityIds, id];
}

function setRefused(criterion: RuleCriterion, id: string, refused: boolean) {
  if (criterion.origin !== "analysis") return;
  const others = (criterion.refusedIds ?? []).filter((other) => other !== id);
  criterion.refusedIds = refused ? [...others, id] : others;
}

function removeEntity(criterion: RuleCriterion, id: string) {
  if (criterion.origin !== "analysis") return;
  criterion.entityIds = criterion.entityIds.filter((other) => other !== id);
  if (!criterion.entityIds.length) remove(criterion.id);
}

/** Retrouver une entité en décrivant l'information : seules les entités des analyses servent, rien n'est extrait. */
const wanted = ref("");
const matching = computed(() => similarToName(wanted.value));

function use(id: string, name: string) {
  add({ id: newId(), origin: "analysis", name, entityIds: [id] });
  wanted.value = "";
}

/** La ou les analyses qui définissent les entités du critère. */
function originLabel(criterion: RuleCriterion) {
  if (criterion.origin !== "analysis") return CRITERION_ORIGINS[criterion.origin];
  const names = analysesOf(criterion.entityIds);
  return names.length > 2 ? `${names.length} analyses` : `Analyse ${names.join(", ")}`;
}

const has = (origin: RuleCriterion["origin"]) => criteria.value.some((c) => c.origin === origin);
</script>

<template>
  <fieldset class="criteria">
    <legend class="fr-text--md fr-mb-1w">Les dossiers doivent avoir en commun (tous les critères à la fois)</legend>

    <p v-if="!criteria.length" class="fr-text--sm">Aucun critère pour le moment.</p>
    <div v-for="criterion in criteria" :key="criterion.id" class="criteria__card">
      <div class="criteria__header">
        <strong class="fr-text--sm fr-mb-0">{{ criterion.name }}</strong>
        <span class="fr-badge fr-badge--sm fr-badge--no-icon">{{ originLabel(criterion) }}</span>
        <button type="button" class="fr-link fr-text--sm criteria__remove" :aria-label="`Retirer le critère ${criterion.name}`" @click="remove(criterion.id)">Retirer</button>
      </div>

      <template v-if="criterion.origin === 'analysis'">
        <p class="criteria__hint">Valeurs tenues pour équivalentes :</p>
        <ul class="fr-tags-group">
          <li v-for="id in criterion.entityIds" :key="id">
            <button type="button" class="fr-tag fr-tag--sm fr-tag--dismiss" :aria-label="`Retirer ${labelOf(id)}`" @click="removeEntity(criterion, id)">{{ labelOf(id) }}</button>
          </li>
        </ul>
        <label class="fr-sr-only" :for="`equivalent-${criterion.id}`">Ajouter une entité équivalente à {{ criterion.name }}</label>
        <select :id="`equivalent-${criterion.id}`" class="fr-select" @change="addEquivalent(criterion, $event)">
          <option value="">Ajouter une entité équivalente…</option>
          <optgroup v-for="analyse in analyses" :key="analyse.name" :label="analyse.name">
            <option v-for="entity in analyse.entities" :key="entity.id" :value="entity.id" :disabled="criterion.entityIds.includes(entity.id)">{{ entity.name }} ({{ entity.type }})</option>
          </optgroup>
        </select>
        <EquivalenceSuggestions
          :entity-ids="criterion.entityIds"
          :refused-ids="criterion.refusedIds ?? []"
          @accept="accept(criterion, $event)"
          @refuse="setRefused(criterion, $event, true)"
          @reconsider="setRefused(criterion, $event, false)"
        />
      </template>

    </div>

    <label class="fr-label" for="criterion-from-analyses">Ajouter depuis les entités des analyses</label>
    <select id="criterion-from-analyses" class="fr-select fr-mb-1w" @change="addFromAnalyses">
      <option value="">Choisir une entité…</option>
      <optgroup v-for="analyse in analyses" :key="analyse.name" :label="analyse.name">
        <option v-for="entity in analyse.entities" :key="entity.id" :value="entity.id">{{ entity.name }} ({{ entity.type }})</option>
      </optgroup>
    </select>

    <label class="fr-label" for="criterion-search">Ou décrire l'information recherchée</label>
    <input id="criterion-search" v-model="wanted" class="fr-input fr-mb-1w" type="search" placeholder="Numéro de permis, adresse…" />
    <div v-if="wanted.trim().length > 3" role="status">
      <template v-if="matching.length">
        <p class="criteria__hint">Entités des analyses qui y ressemblent :</p>
        <ul class="fr-tags-group">
          <li v-for="entity in matching" :key="entity.id">
            <button type="button" class="fr-tag fr-tag--sm" :aria-label="`Utiliser ${entity.id}`" @click="use(entity.id, entity.name)">{{ entity.id }}</button>
          </li>
        </ul>
      </template>
      <p v-else class="criteria__hint fr-mb-1w">
        Aucune analyse n'extrait cette information. Pour la rapprocher, ajoutez-la à une analyse puis relancez ses dossiers.
      </p>
    </div>

    <div class="criteria__others">
      <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" :disabled="has('file')" @click="add({ id: newId(), origin: 'file', name: 'Même fichier' })">Même fichier</button>
    </div>
  </fieldset>
</template>

<style scoped>
.criteria {
  margin: 1rem 0 1.5rem;
  padding: 0;
  border: 0;
}

.criteria__card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
}

.criteria__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.criteria__remove {
  margin-left: auto;
}

.criteria__hint {
  margin: 0;
  color: var(--text-mention-grey);
  font-size: 0.8125rem;
}

.criteria__others {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
</style>
