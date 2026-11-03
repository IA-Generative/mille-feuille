<script setup lang="ts">
import { useTheme } from '@/composables/useTheme';
import type { Theme } from '@/types/profile';
import moonPictogram from "@gouvfr/dsfr/dist/artwork/pictograms/environment/moon.svg?no-inline";
import sunPictogram from "@gouvfr/dsfr/dist/artwork/pictograms/environment/sun.svg?no-inline";
import systemPictogram from "@gouvfr/dsfr/dist/artwork/pictograms/system/system.svg?no-inline";

const { theme, setTheme } = useTheme()

const options: { value: Theme; label: string; hint: string, pictogram: string }[] = [
    { value: "light", label: "Thème clair", hint: "Fond clair, texte sombre", pictogram: sunPictogram },
    { value: "dark", label: "Thème sombre", hint: "Fond sombre, texte clair", pictogram: moonPictogram },
    { value: "system", label: "Système", hint: "Utilise les paramètres de votre appareil", pictogram: systemPictogram},
];
</script>

<template>
    <fieldset class="fr-fieldset" aria-labelledby="theme-choice-legend">
        <legend id="theme-choice-legend" class="fr-fieldset__legend fr-fieldset__legend--regular">
            Choisissez un thème pour personnaliser l'apparence du site.
        </legend>
        <DsfrRadioButton
            v-for="option in options"
            :key="option.value"
            :model-value="theme"
            :value="option.value"
            name="theme"
            :label="option.label"
            :hint="option.hint"
            :svg-path="option.pictogram"
            rich
            @update:model-value="setTheme(option.value)"
        />
    </fieldset>
</template>
