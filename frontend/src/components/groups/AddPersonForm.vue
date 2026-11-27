<script setup lang="ts">
/** Ajouter une personne connue (choisie par son nom) ou une adresse e-mail. */
import { computed, ref, useId, watch } from "vue";

const props = defineProps<{
  roles: { id: string; name: string; assignable?: boolean }[];
  /** Cherche des personnes connues par leur nom ; sans elle, on ne saisit que des adresses. */
  search?: (query: string) => Promise<{ id: string; name: string }[]>;
  error?: string;
}>();
const emit = defineEmits<{ add: [who: { email: string } | { userId: string }, roleId: string, label: string] }>();

const id = useId();
const value = ref("");
const roleId = ref("");
const invalid = ref(false);
const suggestions = ref<{ id: string; name: string }[]>([]);

const offered = computed(() => props.roles.filter((r) => r.assignable !== false));
// Par défaut, le premier rôle qui n'administre pas le groupe, s'il y en a un.
watch(
  offered,
  (list) => {
    if (!list.some((r) => r.id === roleId.value)) roleId.value = (list.find((r) => r.name === "Instructeur") ?? list.at(-1))?.id ?? "";
  },
  { immediate: true },
);

let latest = 0;
watch(value, async (text) => {
  if (!props.search || text.includes("@") || text.trim().length < 2) return;
  const request = ++latest;
  const found = await props.search(text.trim()).catch(() => []);
  if (request === latest) suggestions.value = found;
});

function submit() {
  const text = value.value.trim();
  const person = suggestions.value.find((p) => p.name === text);
  invalid.value = !person && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text);
  if (invalid.value || !roleId.value) return;
  emit("add", person ? { userId: person.id } : { email: text }, roleId.value, text);
  value.value = "";
}
</script>

<template>
  <div>
    <form class="add-person" novalidate @submit.prevent="submit">
      <label class="fr-sr-only" :for="`${id}-who`">Personne à ajouter</label>
      <input :id="`${id}-who`" v-model="value" class="fr-input add-person__who" :placeholder="search ? 'Nom ou adresse e-mail' : 'Adresse e-mail'" :list="`${id}-people`" />
      <datalist :id="`${id}-people`">
        <option v-for="p in suggestions" :key="p.id" :value="p.name" />
      </datalist>
      <label class="fr-sr-only" :for="`${id}-role`">Rôle de la personne ajoutée</label>
      <select :id="`${id}-role`" v-model="roleId" class="fr-select add-person__role">
        <option v-for="role in offered" :key="role.id" :value="role.id">{{ role.name }}</option>
      </select>
      <button type="submit" class="fr-btn fr-btn--secondary">Ajouter</button>
    </form>
    <p v-if="invalid || error" class="fr-error-text" role="alert">
      {{ invalid ? "Choisissez une personne proposée ou saisissez une adresse e-mail." : error }}
    </p>
  </div>
</template>

<style scoped>
.add-person {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.add-person__who {
  flex: 1;
  min-width: 14rem;
}

.add-person__role {
  width: auto;
}
</style>
