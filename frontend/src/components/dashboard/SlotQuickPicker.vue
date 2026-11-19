<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { apiFetch } from "@/utils/api";

// Planification en deux clics : on touche une heure de l'agenda, puis on choisit
// le dossier. Le créneau d'une heure est créé aussitôt (modifiable ensuite).
// Tous les dossiers visibles sont proposés, pas seulement les miens : c'est à la personne de décider
// ce qu'elle met dans son agenda.

interface Candidate {
  id: string;
  name: string;
  status: string;
  overdue: boolean;
}

const props = defineProps<{
  /** Dossiers qui ont déjà mon créneau : le choisir l'écraserait, on ne les propose pas. */
  plannedIds: string[];
  /** Libellé de l'heure choisie (ex. « 14:00 »). */
  timeLabel: string;
}>();

const emit = defineEmits<{
  pick: [dossierId: string];
  close: [];
}>();

const search = ref("");
const input = ref<HTMLInputElement | null>(null);
const loaded = ref<Candidate[]>([]);
const loading = ref(true);
const failed = ref(false);

let timer: ReturnType<typeof setTimeout> | undefined;
let requestId = 0;

/** Recherche côté serveur (nom contenant le texte), les échéances les plus proches d'abord. */
async function load() {
  const id = ++requestId;
  loading.value = true;
  failed.value = false;
  const query = new URLSearchParams({ page_size: "30", sort: "due" });
  if (search.value.trim()) query.set("search", search.value.trim());
  try {
    const page = await apiFetch<{ items: any[] }>(`/api/dossiers?${query}`);
    if (id !== requestId) return; // une recherche plus récente a pris le relais
    loaded.value = page.items
      .filter((d) => d.closed_at == null && d.analyse_id)
      .map((d) => ({
        id: d.id,
        name: d.name,
        status: d.workflow_status?.name ?? "",
        overdue: d.due?.level === "overdue",
      }));
  } catch {
    if (id === requestId) failed.value = true;
  } finally {
    if (id === requestId) loading.value = false;
  }
}

watch(search, () => {
  clearTimeout(timer);
  timer = setTimeout(load, 250);
});
onBeforeUnmount(() => clearTimeout(timer));

const results = computed(() => loaded.value.filter((d) => !props.plannedIds.includes(d.id)));

const root = ref<HTMLElement | null>(null);

onMounted(() => {
  load();
  nextTick(() => {
    input.value?.focus({ preventScroll: true });
    root.value?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
});
</script>

<template>
  <div ref="root" class="qp" role="dialog" aria-label="Planifier un dossier" @keydown.esc.stop="emit('close')">
    <div class="qp__head">
      <span class="qp__title">Planifier à {{ timeLabel }}</span>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary-no-outline" @click="emit('close')">
        <VIcon name="ri-close-line" />
        <span class="fr-sr-only">Fermer</span>
      </button>
    </div>

    <input
      ref="input"
      v-model="search"
      type="search"
      class="fr-input qp__search"
      placeholder="Rechercher un dossier…"
      aria-label="Rechercher un dossier"
    />

    <ul v-if="results.length" class="qp__list">
      <li v-for="d in results" :key="d.id">
        <button type="button" class="qp__item" @click="emit('pick', d.id)">
          <span class="qp__name">{{ d.name }}</span>
          <span class="qp__sub">{{ d.status }}</span>
          <span v-if="d.overdue" class="qp__late">En retard</span>
        </button>
      </li>
    </ul>
    <p v-else class="qp__empty" role="status">
      {{ loading ? "Recherche…" : failed ? "Les dossiers n'ont pas pu être chargés." : "Aucun dossier ne correspond." }}
    </p>
  </div>
</template>

<style scoped>
.qp {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.75rem;
  background: var(--background-default-grey);
  box-shadow: var(--lifted-shadow);
}

.qp__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qp__title {
  font-weight: 700;
}

.qp__list {
  display: flex;
  flex-direction: column;
  max-height: 13rem;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  list-style: none;
}

.qp__item {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: 0.375rem;
  background: none;
  color: var(--text-default-grey);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.qp__item:hover,
.qp__item:focus-visible {
  background: var(--background-alt-grey-hover);
}

.qp__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qp__sub {
  flex-shrink: 0;
  font-size: 0.8125rem;
  color: var(--text-mention-grey);
}

.qp__late {
  flex-shrink: 0;
  font-size: 0.75rem;
  color: var(--text-default-error);
}

.qp__empty {
  margin: 0;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}
</style>
