<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import UrgencyRow from "@/components/dashboard/UrgencyRow.vue";
import type { DashboardUrgency } from "@/types/dashboard";
import SlotEditorModal from "@/components/dashboard/SlotEditorModal.vue";
import SlotQuickPicker from "@/components/dashboard/SlotQuickPicker.vue";
import type { SlotDraft } from "@/types/schedule";
import { occurrenceStarts, slotOfUrgency } from "@/utils/recurrence";
import { formatDayLabel } from "@/utils/dates";

const props = defineProps<{ urgencies: DashboardUrgency[]; view: "day" | "month" }>();
const emit = defineEmits<{
  schedule: [dossierId: string, slot: SlotDraft | null];
  "update:view": [view: "day" | "month"];
}>();

const timeOf = (d: Date) => d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

const MAX_CHIPS = 2;
const HOUR_START = 8;
const HOUR_END = 20;
const HOURS = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i);

/** Position verticale dans la frise, en % de sa hauteur (elle s'adapte à l'écran). `hours` = heures depuis HOUR_START. */
const pct = (hours: number) => `${(hours / HOURS.length) * 100}%`;

/** « Jour » (journée heure par heure) ou « Mois » : choisi par le parent. */
const mode = computed(() => props.view);

/** Entrée en cours d'édition (clic sur un bloc de la chronologie). */
const editing = ref<Entry | null>(null);

function onSave(slot: SlotDraft) {
  if (editing.value) emit("schedule", editing.value.u.dossierId, slot);
  editing.value = null;
}

function onRemove() {
  if (editing.value) emit("schedule", editing.value.u.dossierId, null);
  editing.value = null;
}

/** Frise horaire : sa hauteur réelle sert à convertir un glisser (pixels) en minutes. */
const timelineEl = ref<HTMLElement | null>(null);

/** Heure touchée dans la journée : ouvre le choix rapide d'un dossier à y placer. */
const pickerHour = ref<number | null>(null);

/** La fenêtre s'ouvre juste sous l'heure touchée, qui reste visible et surlignée. */
const pickerTop = computed(() =>
  pickerHour.value === null ? "0" : pct(pickerHour.value - HOUR_START + 1),
);
const hourLabel = (h: number) => `${String(h).padStart(2, "0")}:00`;

/** Crée tout de suite un créneau d'une heure à l'heure choisie ; un clic sur le bloc permet de l'affiner. */
function onPick(dossierId: string) {
  if (pickerHour.value === null) return;
  const h = pickerHour.value;
  const start = new Date(`${selectedKey.value}T${String(h).padStart(2, "0")}:00`);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  emit("schedule", dossierId, { start: start.toISOString(), end: end.toISOString(), reminders: [15] });
  pickerHour.value = null;
}

function openDay(key: string) {
  selectedKey.value = key;
  emit("update:view", "day");
}

/** Ligne rouge de l'heure courante (aujourd'hui seulement, dans la plage affichée). */
const nowTop = computed(() => {
  if (selectedKey.value !== todayKey) return null;
  const h = today.getHours() + today.getMinutes() / 60;
  return h >= HOUR_START && h <= HOUR_END ? pct(h - HOUR_START) : null;
});
const WEEKDAYS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."];

const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const today = new Date();
const todayKey = dayKey(today);

/** Premier jour du mois affiché. */
const month = ref(new Date(today.getFullYear(), today.getMonth(), 1));
const selectedKey = ref(todayKey);

const monthLabel = computed(() =>
  month.value.toLocaleDateString("fr-FR", { month: "long", year: "numeric" }),
);

function shiftMonth(delta: number) {
  month.value = new Date(month.value.getFullYear(), month.value.getMonth() + delta, 1);
}

function goToToday() {
  month.value = new Date(today.getFullYear(), today.getMonth(), 1);
  selectedKey.value = todayKey;
}

/** Une ligne de l'agenda : un dossier, à une occurrence de son créneau ou à son échéance. */
interface Entry {
  u: DashboardUrgency;
  /** Début / fin de l'occurrence ; `null` si le dossier n'est pas planifié. */
  start: Date | null;
  end: Date | null;
  /** Clé stable (un créneau récurrent a une entrée par jour). */
  key: string;
}

/** Plage à couvrir : grille du mois affiché + jour sélectionné (qui peut en sortir). */
const range = computed(() => {
  const first = month.value;
  const offset = (first.getDay() + 6) % 7;
  const gridStart = new Date(first.getFullYear(), first.getMonth(), 1 - offset);
  const gridEnd = new Date(first.getFullYear(), first.getMonth() + 1, 7, 23, 59, 59);
  const [y, m, d] = selectedKey.value.split("-").map(Number);
  const sel = new Date(y, m - 1, d);
  const selEnd = new Date(y, m - 1, d, 23, 59, 59);
  return { from: sel < gridStart ? sel : gridStart, to: selEnd > gridEnd ? selEnd : gridEnd };
});

const byDay = computed(() => {
  const map = new Map<string, Entry[]>();
  const add = (key: string, entry: Entry) => map.set(key, [...(map.get(key) ?? []), entry]);

  for (const u of props.urgencies) {
    if (u.plannedStart && u.plannedEnd) {
      const duration = new Date(u.plannedEnd).getTime() - new Date(u.plannedStart).getTime();
      // Un dossier planifié se place à chaque occurrence de son créneau (une seule s'il ne se répète pas).
      for (const occ of occurrenceStarts(new Date(u.plannedStart), u.recurrence, range.value.from, range.value.to)) {
        add(dayKey(occ), { u, start: occ, end: new Date(occ.getTime() + duration), key: `${u.dossierId}|${occ.toISOString()}` });
      }
    } else {
      add(dayKey(new Date(u.dueAt)), { u, start: null, end: null, key: u.dossierId });
    }
  }
  // Dans une journée : créneaux horaires d'abord (par heure), puis le reste.
  for (const items of map.values()) {
    items.sort((a, b) => (a.start?.getTime() ?? Infinity) - (b.start?.getTime() ?? Infinity));
  }
  return map;
});

/** Grille lundi → dimanche couvrant tout le mois, jours des mois voisins inclus. */
const cells = computed(() => {
  const first = month.value;
  const offset = (first.getDay() + 6) % 7; // lundi = 0
  const daysInMonth = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
  const total = Math.ceil((offset + daysInMonth) / 7) * 7;
  return Array.from({ length: total }, (_, i) => {
    const date = new Date(first.getFullYear(), first.getMonth(), i - offset + 1);
    const key = dayKey(date);
    return {
      key,
      day: date.getDate(),
      inMonth: date.getMonth() === first.getMonth(),
      isToday: key === todayKey,
      isPast: key < todayKey,
      items: byDay.value.get(key) ?? [],
      label: formatDayLabel(date),
    };
  });
});

const selectedItems = computed(() => byDay.value.get(selectedKey.value) ?? []);
const selectedLabel = computed(() => {
  const [y, m, d] = selectedKey.value.split("-").map(Number);
  return formatDayLabel(new Date(y, m - 1, d));
});

const isSelectedToday = computed(() => selectedKey.value === todayKey);

function selectedDate() {
  const [y, m, d] = selectedKey.value.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function shiftDay(delta: number) {
  const d = selectedDate();
  d.setDate(d.getDate() + delta);
  selectedKey.value = dayKey(d);
  month.value = new Date(d.getFullYear(), d.getMonth(), 1);
}

const plannedItems = computed(() => selectedItems.value.filter((e) => e.start));
const unplannedItems = computed(() => selectedItems.value.filter((e) => !e.start));

/** Aujourd'hui : dossiers en retard et sans créneau, à replanifier en priorité. */
const overdueToReplan = computed(() =>
  isSelectedToday.value
    ? props.urgencies.filter((u) => !u.plannedStart && dayKey(new Date(u.dueAt)) < todayKey)
    : [],
);

/** Dossiers proposés au choix rapide : sans créneau, les plus urgents d'abord. */
const unplannedCandidates = computed(() =>
  props.urgencies
    .filter((u) => !u.plannedStart)
    .sort((a, b) => Number(b.level === "overdue") - Number(a.level === "overdue")),
);

/** À planifier : dossiers sans créneau ce jour-là, plus ceux en retard (aujourd'hui). */
const toPlan = computed(() => [...overdueToReplan.value, ...unplannedItems.value.map((e) => e.u)]);
const toPlanOverdue = computed(() => toPlan.value.filter((u) => u.level === "overdue").length);

/** Blocs de la journée : position verticale selon l'heure, colonnes si chevauchement. */
const blocks = computed(() => {
  const laneEnds: number[] = [];
  const placed = plannedItems.value.map((e) => {
    const u = e;
    const start = e.start!;
    const end = e.end!;
    const startH = Math.max(HOUR_START, start.getHours() + start.getMinutes() / 60);
    const endH = Math.min(HOUR_END, end.getHours() + end.getMinutes() / 60);
    let lane = laneEnds.findIndex((e) => e <= startH);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = endH;
    return { u, startH, endH, lane };
  });
  return placed.map(({ u, startH, endH, lane }) => ({
    e: u,
    startH,
    style: {
      top: pct(startH - HOUR_START),
      height: pct(Math.max(endH - startH, 0.5)),
      left: `${(lane / laneEnds.length) * 100}%`,
      width: `${100 / laneEnds.length}%`,
    },
  }));
});

// ---------------------------------------------------------------------------
// Déplacer un créneau : glisser un bloc (pas de 15 min) ou Alt + ↑ / ↓ au clavier
// ---------------------------------------------------------------------------

const SNAP_MIN = 15;
const MIN_MS = 60_000;

/** Déplacement en cours : minutes de décalage proposées pour le bloc `key`. */
const drag = ref<{ key: string; minutes: number } | null>(null);
let dragOrigin: { y: number; moved: boolean; entry: Entry } | null = null;
let justDragged = false;

/** Décalage autorisé : le bloc reste entre HOUR_START et HOUR_END. */
function clampShift(e: Entry, minutes: number) {
  const startMin = e.start!.getHours() * 60 + e.start!.getMinutes();
  const endMin = e.end!.getHours() * 60 + e.end!.getMinutes();
  return Math.max(HOUR_START * 60 - startMin, Math.min(HOUR_END * 60 - endMin, minutes));
}

/** Décale tout le créneau (et sa série s'il se répète) de `minutes`. */
function moveEntry(e: Entry, minutes: number) {
  if (!minutes) return;
  const slot = slotOfUrgency(e.u);
  if (!slot) return;
  const shift = (iso: string) => new Date(new Date(iso).getTime() + minutes * MIN_MS).toISOString();
  emit("schedule", e.u.dossierId, { ...slot, start: shift(slot.start), end: shift(slot.end) });
}

function onBlockDown(ev: PointerEvent, e: Entry) {
  if (ev.button !== 0) return;
  (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
  dragOrigin = { y: ev.clientY, moved: false, entry: e };
}

function onBlockMove(ev: PointerEvent) {
  if (!dragOrigin) return;
  const dy = ev.clientY - dragOrigin.y;
  if (!dragOrigin.moved && Math.abs(dy) < 4) return;
  dragOrigin.moved = true;
  const hourPx = (timelineEl.value?.clientHeight ?? 0) / HOURS.length;
  if (!hourPx) return;
  const raw = (dy / hourPx) * 60;
  const minutes = clampShift(dragOrigin.entry, Math.round(raw / SNAP_MIN) * SNAP_MIN);
  drag.value = { key: dragOrigin.entry.key, minutes };
}

function onBlockUp() {
  if (dragOrigin?.moved && drag.value) {
    moveEntry(dragOrigin.entry, drag.value.minutes);
    // Le « click » qui suit le relâchement ne doit pas ouvrir l'éditeur.
    justDragged = true;
    setTimeout(() => (justDragged = false), 0);
  }
  dragOrigin = null;
  drag.value = null;
}

function onBlockClick(e: Entry) {
  if (!justDragged) editing.value = e;
}

function onBlockKey(ev: KeyboardEvent, e: Entry) {
  if (!ev.altKey) return;
  if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
    ev.preventDefault();
    moveEntryDays(e, ev.key === "ArrowLeft" ? -1 : 1);
  } else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
    ev.preventDefault();
    moveEntry(e, clampShift(e, ev.key === "ArrowUp" ? -SNAP_MIN : SNAP_MIN));
  }
}

const shiftOf = (e: Entry) => (drag.value?.key === e.key ? drag.value.minutes : 0);
const shownStart = (e: Entry) => new Date(e.start!.getTime() + shiftOf(e) * MIN_MS);
const shownEnd = (e: Entry) => new Date(e.end!.getTime() + shiftOf(e) * MIN_MS);

/** Décale le créneau (et sa série) de `days` jours en gardant l'heure ; les jours de répétition suivent. */
function moveEntryDays(e: Entry, days: number) {
  if (!days) return;
  const slot = slotOfUrgency(e.u);
  if (!slot) return;
  const shift = (iso: string) => {
    const d = new Date(iso);
    d.setDate(d.getDate() + days);
    return d.toISOString();
  };
  const weekdays = slot.recurrence?.weekdays?.map((w) => (((w + days) % 7) + 7) % 7).sort((a, b) => a - b);
  emit("schedule", e.u.dossierId, {
    ...slot,
    start: shift(slot.start),
    end: shift(slot.end),
    recurrence: slot.recurrence ? { ...slot.recurrence, weekdays } : undefined,
  });
}

const parseKey = (key: string) => {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const daysBetween = (from: string, to: string) =>
  Math.round((parseKey(to).getTime() - parseKey(from).getTime()) / 86_400_000);

/** Glisser une pastille du mois vers un autre jour. */
const chipDrag = ref<{ key: string; name: string; x: number; y: number; overKey: string | null } | null>(null);
let chipOrigin: { x: number; y: number; moved: boolean; entry: Entry } | null = null;

function cellKeyAt(x: number, y: number) {
  return (document.elementFromPoint(x, y)?.closest("[data-day]") as HTMLElement | null)?.dataset.day ?? null;
}

function onChipDown(ev: PointerEvent, e: Entry) {
  if (ev.button !== 0 || !e.start) return;
  (ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId);
  chipOrigin = { x: ev.clientX, y: ev.clientY, moved: false, entry: e };
}

function onChipMove(ev: PointerEvent) {
  if (!chipOrigin) return;
  if (!chipOrigin.moved && Math.hypot(ev.clientX - chipOrigin.x, ev.clientY - chipOrigin.y) < 5) return;
  chipOrigin.moved = true;
  chipDrag.value = {
    key: chipOrigin.entry.key,
    name: chipOrigin.entry.u.dossierName,
    x: ev.clientX,
    y: ev.clientY,
    overKey: cellKeyAt(ev.clientX, ev.clientY),
  };
}

function onChipUp(ev: PointerEvent) {
  if (chipOrigin?.moved) {
    const target = cellKeyAt(ev.clientX, ev.clientY);
    if (target) moveEntryDays(chipOrigin.entry, daysBetween(dayKey(chipOrigin.entry.start!), target));
    justDragged = true;
    setTimeout(() => (justDragged = false), 0);
  }
  chipOrigin = null;
  chipDrag.value = null;
}

function onCellClick(key: string) {
  if (!justDragged) openDay(key);
}

function cellLabel(c: (typeof cells.value)[number]) {
  const n = c.items.length;
  return n === 0 ? c.label : `${c.label} : ${n} dossier${n > 1 ? "s" : ""} à traiter`;
}
</script>

<template>
  <div class="cal">
    <div class="cal__toolbar">
      <div v-if="mode === 'month'" class="cal__nav">
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="shiftMonth(-1)">
          <VIcon name="ri-arrow-left-s-line" />
          <span class="fr-sr-only">Mois précédent</span>
        </button>
        <h3 class="cal__month" aria-live="polite">{{ monthLabel }}</h3>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="shiftMonth(1)">
          <VIcon name="ri-arrow-right-s-line" />
          <span class="fr-sr-only">Mois suivant</span>
        </button>
      </div>
      <div v-else class="cal__nav">
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="shiftDay(-1)">
          <VIcon name="ri-arrow-left-s-line" />
          <span class="fr-sr-only">Jour précédent</span>
        </button>
        <h3 class="cal__month" aria-live="polite">{{ isSelectedToday ? "Aujourd'hui" : selectedLabel }}</h3>
        <button type="button" class="fr-btn fr-btn--sm fr-btn--tertiary" @click="shiftDay(1)">
          <VIcon name="ri-arrow-right-s-line" />
          <span class="fr-sr-only">Jour suivant</span>
        </button>
      </div>
      <button type="button" class="fr-btn fr-btn--sm fr-btn--secondary" @click="goToToday">Aujourd'hui</button>
    </div>

    <!-- Vue Jour : la journée heure par heure -->
    <div v-if="mode === 'day'" class="cal__day-view">
      <p class="cal__hint">
        <VIcon name="ri-cursor-line" /> Touchez une heure pour y placer un dossier. Cliquez sur un bloc pour le modifier, glissez-le pour le déplacer.
      </p>
      <div class="cal__scroll">
      <div ref="timelineEl" class="cal__timeline" :style="{ '--hours': HOURS.length }">
        <button
          v-for="h in HOURS"
          :key="h"
          type="button"
          class="cal__hour"
          :class="{ 'cal__hour--active': pickerHour === h }"
          :aria-label="`Planifier un dossier à ${hourLabel(h)}`"
          @click="pickerHour = h"
        >
          <span class="cal__hour-label">{{ hourLabel(h) }}</span>
          <span class="cal__add" aria-hidden="true"><VIcon name="ri-add-line" /> Planifier un dossier</span>
        </button>
      <div v-if="nowTop" class="cal__now" :style="{ top: nowTop }" aria-hidden="true" />
        <div class="cal__blocks">
            <div
              v-for="b in blocks"
              :key="b.e.key"
              class="cal__block"
              :class="[
                b.e.u.level === 'overdue' ? 'cal__block--overdue' : 'cal__block--soon',
                { 'cal__block--drag': drag?.key === b.e.key },
              ]"
              :style="{ ...b.style, top: pct(b.startH - HOUR_START + shiftOf(b.e) / 60) }"
              title="Cliquer pour modifier · glisser pour déplacer (Alt + flèches au clavier)"
              @pointerdown="onBlockDown($event, b.e)"
              @pointermove="onBlockMove"
              @pointerup="onBlockUp"
              @pointercancel="onBlockUp"
              @keydown="onBlockKey($event, b.e)"
              @click="onBlockClick(b.e)"
            >
            <button type="button" class="cal__block-main">
              <span class="cal__block-time">
                {{ timeOf(shownStart(b.e)) }}–{{ timeOf(shownEnd(b.e)) }}
                <VIcon v-if="b.e.u.recurrence" name="ri-repeat-line" aria-label="Se répète" />
              </span>
              <span class="cal__block-title">{{ b.e.u.dossierName }}</span>
            </button>
            <RouterLink
              :to="`/dossiers/${b.e.u.dossierId}`"
              class="cal__block-open"
              title="Ouvrir le dossier"
              @pointerdown.stop
              @click.stop
            >
              <VIcon name="ri-folder-open-line" />
              <span class="fr-sr-only">Ouvrir le dossier {{ b.e.u.dossierName }}</span>
            </RouterLink>
          </div>
        </div>
        <SlotQuickPicker
          v-if="pickerHour !== null"
          class="cal__picker"
          :style="{ top: pickerTop }"
          :candidates="unplannedCandidates"
          :time-label="hourLabel(pickerHour)"
          @pick="onPick"
          @close="pickerHour = null"
        />
      </div>
    </div>

      <details v-if="toPlan.length" class="cal__toplan">
        <summary>
          À planifier · {{ toPlan.length }}
          <span v-if="toPlanOverdue" class="cal__toplan-late">dont {{ toPlanOverdue }} en retard</span>
        </summary>
        <ul class="cal__list">
          <li v-for="u in toPlan" :key="u.dossierId">
            <UrgencyRow :urgency="u" :default-date="selectedKey" @schedule="(id, slot) => emit('schedule', id, slot)" />
          </li>
        </ul>
      </details>
    </div>

    <!-- Vue Mois -->
    <template v-else>
    <div class="cal__scroll">
      <div class="cal__grid" role="grid" :aria-label="`Calendrier de ${monthLabel}`">
        <div v-for="w in WEEKDAYS" :key="w" class="cal__weekday" role="columnheader">{{ w }}</div>
        <button
          v-for="c in cells"
          :key="c.key"
          type="button"
          role="gridcell"
          class="cal__cell"
          :class="{
            'cal__cell--out': !c.inMonth,
            'cal__cell--today': c.isToday,
            'cal__cell--selected': c.key === selectedKey,
            'cal__cell--drop': chipDrag?.overKey === c.key,
          }"
          :data-day="c.key"
          :aria-label="cellLabel(c)"
          :aria-selected="c.key === selectedKey"
          @click="onCellClick(c.key)"
        >
          <span class="cal__day">{{ c.day }}</span>
          <span v-if="c.items.length" class="cal__chips" aria-hidden="true">
            <span
              v-for="e in c.items.slice(0, MAX_CHIPS)"
              :key="e.key"
              class="cal__chip"
              :class="[e.u.level === 'overdue' ? 'cal__chip--overdue' : 'cal__chip--soon', { 'cal__chip--movable': e.start }]"
              @pointerdown="onChipDown($event, e)"
              @pointermove="onChipMove"
              @pointerup="onChipUp"
              @pointercancel="onChipUp"
            ><span v-if="e.start" class="cal__chip-time">{{ timeOf(e.start) }}</span>{{ e.u.dossierName }}</span>
            <span v-if="c.items.length > MAX_CHIPS" class="cal__more">+{{ c.items.length - MAX_CHIPS }} autre{{ c.items.length - MAX_CHIPS > 1 ? "s" : "" }}</span>
          </span>
          <span v-if="c.items.length" class="cal__dot" aria-hidden="true">{{ c.items.length }}</span>
        </button>
      </div>
    </div>
    <p v-if="chipDrag" class="cal__ghost" :style="{ left: `${chipDrag.x + 12}px`, top: `${chipDrag.y + 12}px` }" aria-hidden="true">
      {{ chipDrag.name }}
    </p>

    </template>

    <SlotEditorModal
      v-if="editing"
      :dossier-name="editing.u.dossierName"
      :dossier-id="editing.u.dossierId"
      :initial="slotOfUrgency(editing.u)"
      :default-date="selectedKey"
      @save="onSave"
      @remove="onRemove"
      @close="editing = null"
    />
  </div>
</template>

<style scoped>
/* Vue Jour : .cal et .cal__day-view transmettent la hauteur à la frise (sans effet quand la page n'est pas bornée). */
.cal,
.cal__day-view {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

/* La frise défile ici quand l'écran est trop bas ; min-height évite que l'ouverture de « À planifier » l'écrase. */
.cal__scroll {
  flex: 1;
  min-height: 14rem;
  overflow-y: auto;
}

.cal__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.cal__timeline {
  position: relative;
  display: grid;
  grid-template-rows: repeat(var(--hours), 1fr);
  height: 100%;
  min-height: calc(var(--hours) * 1.75rem); /* sous ce seuil, .cal__scroll défile */
  border-top: 1px solid var(--border-default-grey);
}

.cal__hour {
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 0;
  border: none;
  border-bottom: 1px solid var(--border-default-grey);
  background: none;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.cal__hour:hover,
.cal__hour:focus-visible {
  background: var(--background-alt-blue-france);
}

.cal__hint {
  margin: 0.75rem 0 0.5rem;
  font-size: 0.875rem;
  color: var(--text-mention-grey);
}

.cal__add {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: 0.5rem;
  padding: 0.125rem 0.625rem;
  border-radius: 1rem;
  background: var(--background-contrast-info);
  color: var(--text-action-high-blue-france);
  font-size: 0.75rem;
  font-weight: 600;
  opacity: 0;
  transition: opacity 0.12s;
}

.cal__hour:hover .cal__add,
.cal__hour:focus-visible .cal__add,
.cal__hour--active .cal__add {
  opacity: 1;
}

/* Écrans tactiles : pas de survol, l'invitation reste visible mais discrète. */
@media (hover: none) {
  .cal__add {
    opacity: 0.7;
  }
}

.cal__hour--active {
  background: var(--background-alt-blue-france);
}

.cal__picker {
  position: absolute;
  left: 3.5rem;
  right: 0.5rem;
  z-index: 3;
  max-width: 26rem;
}

.cal__hour-label {
  display: inline-block;
  width: 3.25rem;
  padding: 0.125rem 0.25rem;
  font-size: 0.75rem;
  color: var(--text-mention-grey);
}

.cal__blocks {
  position: absolute;
  inset: 0 0 0 3.5rem;
  /* Les clics passent à l'heure en dessous, sauf sur les blocs. */
  pointer-events: none;
}

.cal__block {
  position: absolute;
  container-type: size;
  container-name: block;
  display: flex;
  align-items: flex-start;
  overflow: hidden;
  pointer-events: auto;
  touch-action: none;
  user-select: none;
  box-sizing: border-box;
  border-left: 4px solid;
  border-radius: 0.375rem;
  color: var(--text-default-grey);
  font-size: 0.8125rem;
  line-height: 1.25;
  cursor: grab;
}

.cal__block-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
  height: 100%;
  padding: 0.25rem 0.25rem 0.25rem 0.5rem;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: inherit;
}

/* Bloc court (< 3,2 rem de haut) : « 09:00–10:00  Titre » sur une ligne. Remplace l'ancien calcul en JS. */
@container block (max-height: 3.2rem) {
  .cal__block-main {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
    padding-block: 0.125rem;
  }
}

.cal__block-open {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: flex-start;
  width: 1.75rem;
  height: 1.75rem;
  margin: 0.125rem 0.125rem 0 0;
  border-radius: 0.375rem;
  background: rgb(255 255 255 / 70%);
  background-image: none;
  color: var(--text-action-high-blue-france);
}

.cal__block-open:hover,
.cal__block-open:focus-visible {
  background: var(--background-default-grey);
}

.cal__now {
  position: absolute;
  left: 3.25rem;
  right: 0;
  height: 2px;
  background: var(--background-flat-error);
  z-index: 2;
  pointer-events: none;
}

.cal__now::before {
  content: "";
  position: absolute;
  left: -0.3125rem;
  top: -0.25rem;
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 50%;
  background: var(--background-flat-error);
}

.cal__toplan {
  margin-top: 1.25rem;
}

.cal__toplan > summary {
  cursor: pointer;
  font-weight: 600;
}

.cal__toplan-late {
  margin-left: 0.5rem;
  font-weight: 400;
  color: var(--text-default-error);
}

.cal__toplan .cal__list {
  margin-top: 0.5rem;
}

.cal__block--drag {
  z-index: 4;
  cursor: grabbing;
  box-shadow: 0 6px 18px rgb(0 0 0 / 25%);
}

.cal__block--overdue {
  border-color: var(--background-flat-error);
  background: var(--background-contrast-error);
}

.cal__block--soon {
  border-color: var(--background-flat-warning);
  background: var(--background-contrast-warning);
}

.cal__block-time {
  flex-shrink: 0;
  font-size: 0.75rem;
  font-weight: 700;
  white-space: nowrap;
}

.cal__block-title {
  min-width: 0;
  overflow: hidden;
  font-size: 0.875rem;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cal__nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cal__month {
  min-width: 10rem;
  margin: 0;
  font-size: 1.125rem;
  text-align: center;
}

.cal__month::first-letter {
  text-transform: uppercase;
}

.cal__grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  grid-template-rows: auto; /* ligne des jours de la semaine */
  grid-auto-rows: minmax(4.5rem, 1fr); /* les semaines se partagent la hauteur disponible */
  min-height: 100%;
  border-top: 1px solid var(--border-default-grey);
  border-left: 1px solid var(--border-default-grey);
}

.cal__weekday {
  padding: 0.375rem;
  border-right: 1px solid var(--border-default-grey);
  border-bottom: 1px solid var(--border-default-grey);
  background: var(--background-alt-grey);
  font-size: 0.75rem;
  font-weight: 700;
  text-align: center;
  text-transform: uppercase;
  color: var(--text-mention-grey);
}

.cal__cell {
  position: relative;
  container-type: size;
  container-name: cell;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0.25rem;
  min-height: 6.5rem;
  padding: 0.375rem;
  border: none;
  border-right: 1px solid var(--border-default-grey);
  border-bottom: 1px solid var(--border-default-grey);
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  min-width: 0;
}

.cal__cell:hover {
  background: var(--background-alt-grey-hover);
}

.cal__cell--out {
  background: var(--background-alt-grey);
  color: var(--text-disabled-grey);
}

.cal__cell--selected {
  outline: 2px solid var(--border-active-blue-france);
  outline-offset: -2px;
  z-index: 1;
}

.cal__day {
  align-self: flex-start;
  min-width: 1.5rem;
  padding: 0 0.25rem;
  border-radius: 0.75rem;
  font-size: 0.8125rem;
  font-weight: 600;
  line-height: 1.5rem;
  text-align: center;
}

.cal__cell--today .cal__day {
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
}

.cal__chips {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.cal__chip {
  overflow: hidden;
  padding: 0.0625rem 0.375rem;
  border-left: 3px solid;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cal__chip--overdue {
  border-color: var(--background-flat-error);
  background: var(--background-contrast-error);
}

.cal__chip--soon {
  border-color: var(--background-flat-warning);
  background: var(--background-contrast-warning);
}

.cal__chip--movable {
  cursor: grab;
  touch-action: none;
}

.cal__cell--drop {
  background: var(--background-alt-blue-france);
  outline: 2px dashed var(--border-active-blue-france);
  outline-offset: -2px;
}

.cal__ghost {
  position: fixed;
  z-index: 10;
  max-width: 14rem;
  margin: 0;
  padding: 0.25rem 0.625rem;
  overflow: hidden;
  border-radius: 0.375rem;
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
  font-size: 0.8125rem;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-shadow: 0 6px 18px rgb(0 0 0 / 25%);
  pointer-events: none;
}

.cal__chip-time {
  margin-right: 0.375rem;
  font-weight: 700;
}

.cal__more {
  font-size: 0.6875rem;
  color: var(--text-mention-grey);
}

/* Petits écrans : le nombre remplace les pastilles */
.cal__dot {
  display: none;
  align-self: center;
  min-width: 1.25rem;
  border-radius: 0.625rem;
  background: var(--background-flat-info);
  color: var(--text-inverted-info);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1.25rem;
  text-align: center;
}

@media (max-width: 48em) {
  .cal__grid {
    grid-auto-rows: minmax(3.5rem, 1fr);
  }

  .cal__chips {
    display: none;
  }

  .cal__dot {
    display: block;
  }
}

/* Case trop basse pour les pastilles (jour + 2 dossiers + « +N autres » ≈ 5,75 rem) : le compteur les remplace. */
@container cell (max-height: 5.75rem) {
  .cal__chips {
    display: none;
  }

  .cal__dot {
    display: block;
  }
}

.cal__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
