<script setup lang="ts">
import type { ToolVisibility } from "@/types/tool";

const visibility = defineModel<ToolVisibility>({ required: true });

const options = [
  { name: "tool-visibility", value: "private", label: "Privé", hint: "Visible par vous seul." },
  { name: "tool-visibility", value: "groups", label: "Mes groupes", hint: "Utilisable par les membres de vos groupes." },
  { name: "tool-visibility", value: "all", label: "Toute la plateforme", hint: "Utilisable par toute personne connectée." },
];
</script>

<template>
  <DsfrRadioButtonSet v-model="visibility" legend="Qui peut utiliser ce serveur" :options="options" small />
</template>
