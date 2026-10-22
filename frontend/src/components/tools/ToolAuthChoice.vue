<script setup lang="ts">
import type { ToolAuthMode } from "@/types/tool";

const mode = defineModel<ToolAuthMode>({ required: true });

const options = [
  {
    name: "tool-auth",
    value: "none",
    label: "Sans authentification",
    hint: "Le serveur est public : il n'identifie personne.",
  },
  {
    name: "tool-auth",
    value: "token_exchange",
    label: "Identité de l'utilisateur",
    hint: "Le serveur reçoit un jeton au nom de la personne qui lance l'agent.",
  },
  {
    name: "tool-auth",
    value: "static_token",
    label: "Jeton statique (bientôt disponible)",
    hint: "Un jeton fourni à l'ajout du serveur, partagé par tous.",
    disabled: true,
  },
];
</script>

<template>
  <DsfrRadioButtonSet v-model="mode" legend="Authentification auprès du serveur" :options="options" small />
</template>
