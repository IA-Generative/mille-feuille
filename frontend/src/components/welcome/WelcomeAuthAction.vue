<script setup lang="ts">
import { useAuth } from "@/composables/useAuth";

withDefaults(defineProps<{ size?: "sm" | "lg" }>(), { size: "lg" });
const { isAuthenticated, loading, login } = useAuth();
</script>

<template>
  <DsfrButton v-if="!isAuthenticated && !loading" label="Se connecter" :size="size" @click="login()" />
  <RouterLink v-else-if="isAuthenticated" to="/analyses" class="fr-btn" :class="`fr-btn--${size}`">
    Accéder à l'application
  </RouterLink>
</template>
