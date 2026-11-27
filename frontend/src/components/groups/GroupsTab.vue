<script setup lang="ts">
/** Liste des groupes et détail du groupe choisi. */
import { computed, onMounted, ref } from "vue";

import GroupDetail from "@/components/groups/GroupDetail.vue";
import GroupModal from "@/components/groups/GroupModal.vue";
import { useAuth } from "@/composables/useAuth";
import { useGroups } from "@/composables/useGroups";
import { userMessage } from "@/utils/api";

const { isAdmin } = useAuth();
const { groups, fetchGroups } = useGroups();

const isLoaded = ref(false);
const error = ref("");
onMounted(async () => {
  try {
    await fetchGroups();
    isLoaded.value = true;
  } catch (cause) {
    error.value = userMessage(cause, "Les groupes n'ont pas pu être chargés.");
  }
});

const chosenId = ref("");
const selected = computed(() => groups.value.find((g) => g.id === chosenId.value) ?? groups.value[0]);

const isModalOpened = ref(false);
const editedId = ref<string | null>(null);

function openModal(id: string | null) {
  editedId.value = id;
  isModalOpened.value = true;
}
</script>

<template>
  <div class="groups-tab">
    <div>
      <p v-if="error" class="fr-error-text" role="alert">{{ error }}</p>
      <p v-else-if="!isLoaded" class="fr-text--sm">Chargement…</p>
      <p v-else-if="!groups.length" class="fr-text--sm">{{ isAdmin ? "Aucun groupe pour le moment." : "Vous n'appartenez à aucun groupe." }}</p>
      <ul v-else class="group-card">
        <li v-for="group in groups" :key="group.id">
          <button
            type="button"
            class="group-card__row"
            :class="{ 'groups-tab__row--selected': group.id === selected?.id }"
            :aria-current="group.id === selected?.id ? 'true' : undefined"
            @click="chosenId = group.id"
          >
            <span class="group-card__main">
              <span class="group-card__title">{{ group.name }}</span>
              <span class="group-card__detail">{{ group.memberCount }} membre(s)</span>
            </span>
          </button>
        </li>
      </ul>
      <button v-if="isAdmin" type="button" class="fr-btn fr-btn--secondary fr-btn--sm fr-mt-2w" @click="openModal(null)">
        Créer un groupe
      </button>
    </div>

    <GroupDetail v-if="selected" :key="selected.id" :group-id="selected.id" @edit="openModal(selected.id)" />

    <GroupModal :opened="isModalOpened" :group-id="editedId" @close="isModalOpened = false" @saved="chosenId = $event" />
  </div>
</template>

<style scoped src="./cards.css"></style>
<style scoped>
.groups-tab {
  display: grid;
  grid-template-columns: minmax(14rem, 18rem) 1fr;
  gap: 1.5rem;
  align-items: start;
}

.groups-tab__row--selected {
  background: var(--background-contrast-grey);
}

@media (max-width: 48rem) {
  .groups-tab {
    grid-template-columns: 1fr;
  }
}
</style>
