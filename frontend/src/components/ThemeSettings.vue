<script setup lang="ts">
import { ref } from "vue";

import ThemeChoice from "./ThemeChoice.vue";

const opened = ref(false)
const trigger = ref<HTMLButtonElement | null>(null)
</script>

<template>
    <button
        ref="trigger"
        type="button"
        class="fr-btn fr-btn--tertiary-no-outline fr-btn--sm fr-icon-theme-fill fr-btn--icon-left"
        aria-haspopup="dialog"
        @click="opened = true"
    >
        Paramètres d'affichage
    </button>

    <Teleport to="body">
        <DsfrModal
            :opened="opened"
            title="Paramètres d'affichage"
            :origin="trigger ?? undefined"
            @close="opened = false"
        >
            <ThemeChoice />
        </DsfrModal>
    </Teleport>
</template>