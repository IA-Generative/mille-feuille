<script setup lang="ts">
/**
 * Encart qui signale l'existence d'un tutoriel et permet de l'ouvrir depuis la page.
 * Affiché tant que le tutoriel n'a pas été vu.
 */
import { ref } from "vue";

import { useTutorials } from "@/composables/useTutorials";

const props = defineProps<{ slug: string; title: string; content: string }>();

const { openPanel, isSeen } = useTutorials();

// Valeur figée au chargement : ouvrir le tutoriel le marque « vu », mais l'encart ne doit pas disparaître
// sous les doigts de la personne (le bouton qui a ouvert le panneau doit rester pour récupérer le focus).
// eslint-disable-next-line vue/no-setup-props-reactivity-loss -- lecture volontairement unique
const visible = ref(!isSeen(props.slug));
</script>

<template>
  <DsfrCallout
    v-if="visible"
    :title="title"
    title-tag="p"
    :content="content"
    :button="{ label: 'Ouvrir le tutoriel', secondary: true, onClick: () => openPanel(slug) }"
  />
</template>
