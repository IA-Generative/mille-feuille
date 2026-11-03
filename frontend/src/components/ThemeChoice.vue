<script setup lang="ts">
import { useTheme } from '@/composables/useTheme';
import type { Theme } from '@/types/profile';

const { theme, setTheme } = useTheme()

const options: { value: Theme; label: string; hint: string }[] = [
    { value: "light", label: "Thème clair", hint: "Fond clair, texte sombre" },
    { value: "dark", label: "Thème sombre", hint: "Fond sombre, texte clair" },
    { value: "system", label: "Système", hint: "Utilise les paramètres de votre appareil" },
];
</script>

<template>
    <fieldset class="fr-fieldset" aria-labelledby="theme-choice-legend">
        <legend id="theme-choice-legend" class="fr-fieldset__legend fr-fieldset__legend--regular">
            Choisissez un thème pour personnaliser l'apparence du site.
        </legend>
        <div v-for="option in options" :key="option.value" class="fr-fieldset__element">
            <DsfrRadioButton
                :model-value="theme"
                :value="option.value"
                name="theme"
                :label="option.label"
                :hint="option.hint"
                rich
                @update:model-value="setTheme(option.value)"
            />
        </div>
    </fieldset>
</template>