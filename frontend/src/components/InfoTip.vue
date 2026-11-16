<script setup lang="ts">
// Info-bulle DSFR accessible (clic, focus clavier, Échap) à placer À CÔTÉ d'un libellé.
// Elle complète, elle ne remplace pas : une information essentielle reste en texte visible.
withDefaults(defineProps<{ content: string; label?: string }>(), { label: "Plus d'informations" });
</script>

 <template>
  <DsfrTooltip :content="content">{{ label }}</DsfrTooltip>
 </template>
