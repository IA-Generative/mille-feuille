<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

import {
  MAX_REMINDERS,
  REMINDER_PRESETS,
  REMINDER_UNIT_MINUTES,
  WEEKDAY_INITIALS,
  WEEKDAY_NAMES,
  type Recurrence,
  type RecurrenceUnit,
  type ReminderUnit,
  type SlotDraft,
} from "@/types/schedule";
import { summarizeRecurrence, summarizeReminders, weekdayOf } from "@/utils/recurrence";
import { formatDayLabel } from "@/utils/dates";

const props = defineProps<{
  dossierName: string;
  /** Si fourni, le nom du dossier devient un lien vers celui-ci. */
  dossierId?: string;
  /** Créneau existant à modifier, ou `null` pour en créer un. */
  initial: SlotDraft | null;
  /** Jour proposé pour un nouveau créneau (YYYY-MM-DD). */
  defaultDate: string;
}>();

const emit = defineEmits<{
  save: [slot: SlotDraft];
  remove: [];
  close: [];
}>();

const pad = (n: number) => String(n).padStart(2, "0");
const toDateInput = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const toTimeInput = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const toMinutes = (time: string) => {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
};

// ---------------------------------------------------------------------------
// Quand
// ---------------------------------------------------------------------------

const date = ref(props.defaultDate);
const start = ref("09:00");
const end = ref("10:00");

const DURATIONS = [
  { minutes: 30, label: "30 min" },
  { minutes: 60, label: "1 h" },
  { minutes: 120, label: "2 h" },
  { minutes: 240, label: "Demi-journée" },
];

const duration = computed(() => toMinutes(end.value) - toMinutes(start.value));

function setDuration(minutes: number) {
  const total = Math.min(toMinutes(start.value) + minutes, 23 * 60 + 59);
  end.value = `${pad(Math.floor(total / 60))}:${pad(total % 60)}`;
}

function setDay(offset: number) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  date.value = toDateInput(d);
}

// ---------------------------------------------------------------------------
// Répétition (façon calendrier iOS)
// ---------------------------------------------------------------------------

type RepeatChoice = "none" | "day" | "week" | "biweek" | "month" | "year" | "custom";

const REPEAT_OPTIONS: { value: RepeatChoice; text: string }[] = [
  { value: "none", text: "Jamais" },
  { value: "day", text: "Tous les jours" },
  { value: "week", text: "Toutes les semaines" },
  { value: "biweek", text: "Toutes les 2 semaines" },
  { value: "month", text: "Tous les mois" },
  { value: "year", text: "Tous les ans" },
  { value: "custom", text: "Personnalisé…" },
];

const UNIT_OPTIONS: { value: RecurrenceUnit; one: string; many: string }[] = [
  { value: "day", one: "jour", many: "jours" },
  { value: "week", one: "semaine", many: "semaines" },
  { value: "month", one: "mois", many: "mois" },
  { value: "year", one: "an", many: "ans" },
];

const repeat = ref<RepeatChoice>("none");
const customInterval = ref(1);
const customUnit = ref<RecurrenceUnit>("week");
const customDays = ref<number[]>([]);
const endType = ref<"never" | "until" | "count">("never");
const endDate = ref("");
const endCount = ref(10);

const startDateTime = computed(() => new Date(`${date.value}T${start.value}`));

function toggleDay(day: number) {
  customDays.value = customDays.value.includes(day)
    ? customDays.value.filter((d) => d !== day)
    : [...customDays.value, day].sort((a, b) => a - b);
}

function buildRecurrence(): Recurrence | undefined {
  if (repeat.value === "none") return undefined;
  const endRule: Recurrence["end"] =
    endType.value === "until"
      ? { type: "until", date: endDate.value }
      : endType.value === "count"
        ? { type: "count", count: endCount.value }
        : { type: "never" };
  const wd = weekdayOf(startDateTime.value);
  switch (repeat.value) {
    case "day":
      return { unit: "day", interval: 1, end: endRule };
    case "week":
      return { unit: "week", interval: 1, weekdays: [wd], end: endRule };
    case "biweek":
      return { unit: "week", interval: 2, weekdays: [wd], end: endRule };
    case "month":
      return { unit: "month", interval: 1, end: endRule };
    case "year":
      return { unit: "year", interval: 1, end: endRule };
    default:
      return {
        unit: customUnit.value,
        interval: customInterval.value,
        weekdays: customUnit.value === "week" ? customDays.value : undefined,
        end: endRule,
      };
  }
}

// ---------------------------------------------------------------------------
// Rappels (plusieurs, prédéfinis ou personnalisés)
// ---------------------------------------------------------------------------

interface ReminderRow {
  id: number;
  /** Minutes en chaîne, ou « custom ». */
  preset: string;
  customValue: number;
  customUnit: ReminderUnit;
}

let nextReminderId = 1;
const reminderRows = ref<ReminderRow[]>([]);

function rowFromMinutes(minutes: number): ReminderRow {
  if (REMINDER_PRESETS.some((p) => p.value === minutes)) {
    return { id: nextReminderId++, preset: String(minutes), customValue: 30, customUnit: "minute" };
  }
  const unit: ReminderUnit = minutes % 1440 === 0 ? "day" : minutes % 60 === 0 ? "hour" : "minute";
  return {
    id: nextReminderId++,
    preset: "custom",
    customValue: minutes / REMINDER_UNIT_MINUTES[unit],
    customUnit: unit,
  };
}

const rowMinutes = (r: ReminderRow) =>
  r.preset === "custom" ? r.customValue * REMINDER_UNIT_MINUTES[r.customUnit] : Number(r.preset);

function addReminder() {
  // Propose la première valeur prédéfinie pas encore utilisée.
  const used = new Set(reminderRows.value.map(rowMinutes));
  const free = REMINDER_PRESETS.find((p) => !used.has(p.value)) ?? REMINDER_PRESETS[0];
  reminderRows.value.push(rowFromMinutes(free.value));
}

function removeReminder(id: number) {
  reminderRows.value = reminderRows.value.filter((r) => r.id !== id);
}

// ---------------------------------------------------------------------------
// Initialisation depuis un créneau existant
// ---------------------------------------------------------------------------

function init() {
  const slot = props.initial;
  if (!slot) {
    reminderRows.value = [rowFromMinutes(15)];
    return;
  }
  const s = new Date(slot.start);
  date.value = toDateInput(s);
  start.value = toTimeInput(s);
  end.value = toTimeInput(new Date(slot.end));
  reminderRows.value = slot.reminders.map(rowFromMinutes);

  const rec = slot.recurrence;
  if (!rec) return;
  const wd = weekdayOf(s);
  const onlyStartDay = !rec.weekdays?.length || (rec.weekdays.length === 1 && rec.weekdays[0] === wd);
  if (rec.unit === "day" && rec.interval === 1) repeat.value = "day";
  else if (rec.unit === "week" && rec.interval === 1 && onlyStartDay) repeat.value = "week";
  else if (rec.unit === "week" && rec.interval === 2 && onlyStartDay) repeat.value = "biweek";
  else if (rec.unit === "month" && rec.interval === 1) repeat.value = "month";
  else if (rec.unit === "year" && rec.interval === 1) repeat.value = "year";
  else {
    repeat.value = "custom";
    customUnit.value = rec.unit;
    customInterval.value = rec.interval;
    customDays.value = rec.weekdays ?? [];
  }
  endType.value = rec.end.type;
  if (rec.end.type === "until") endDate.value = rec.end.date;
  if (rec.end.type === "count") endCount.value = rec.end.count;
}
init();

// ---------------------------------------------------------------------------
// Validation, résumé, enregistrement
// ---------------------------------------------------------------------------

const errors = computed(() => {
  const list: string[] = [];
  if (!date.value || !start.value || !end.value) list.push("Renseignez le jour et les deux horaires.");
  else if (duration.value <= 0) list.push("L'heure de fin doit être après l'heure de début.");
  if (repeat.value === "custom") {
    if (!(customInterval.value >= 1)) list.push("L'intervalle de répétition doit être d'au moins 1.");
    if (customUnit.value === "week" && customDays.value.length === 0) list.push("Choisissez au moins un jour de la semaine.");
  }
  if (repeat.value !== "none") {
    if (endType.value === "until" && (!endDate.value || endDate.value < date.value)) {
      list.push("La date de fin de répétition doit être le jour du créneau ou après.");
    }
    if (endType.value === "count" && !(endCount.value >= 1)) list.push("Le nombre d'occurrences doit être d'au moins 1.");
  }
  if (reminderRows.value.some((r) => r.preset === "custom" && !(r.customValue >= 1))) {
    list.push("Un rappel personnalisé doit durer au moins 1.");
  }
  return list;
});

const reminders = computed(() =>
  [...new Set(reminderRows.value.map(rowMinutes))].filter((m) => Number.isFinite(m)).sort((a, b) => a - b),
);

const summary = computed(() => {
  if (!date.value || !start.value) return "";
  const when = formatDayLabel(startDateTime.value);
  const rec = buildRecurrence();
  return [
    `${when}, ${start.value}–${end.value}`,
    rec ? summarizeRecurrence(rec, startDateTime.value) : "Une seule fois",
    summarizeReminders(reminders.value),
  ].join(" · ");
});

function save() {
  if (errors.value.length) return;
  emit("save", {
    start: new Date(`${date.value}T${start.value}`).toISOString(),
    end: new Date(`${date.value}T${end.value}`).toISOString(),
    recurrence: buildRecurrence(),
    reminders: reminders.value,
  });
}

const actions = computed(() => [
  { label: "Enregistrer", onClick: save, disabled: errors.value.length > 0 },
  { label: "Annuler", secondary: true, onClick: () => emit("close") },
  ...(props.initial ? [{ label: "Supprimer le créneau", tertiary: true, onClick: () => emit("remove") }] : []),
]);
</script>

<template>
  <DsfrModal
    :opened="true"
    :title="initial ? 'Modifier le créneau' : 'Planifier le traitement'"
    icon="ri-calendar-event-line"
    size="lg"
    :actions="actions"
    @close="emit('close')"
  >
    <p class="slot__dossier">
      <RouterLink v-if="dossierId" :to="`/dossiers/${dossierId}`">{{ dossierName }}</RouterLink>
      <template v-else>{{ dossierName }}</template>
    </p>
    <p class="slot__summary" aria-live="polite">{{ summary }}</p>

    <!-- QUAND -->
    <section class="slot__group" aria-labelledby="slot-when">
      <h3 id="slot-when" class="slot__heading">Quand</h3>
      <div class="slot__row">
        <label for="slot-date">Jour</label>
        <div class="slot__control">
          <input id="slot-date" v-model="date" type="date" class="fr-input" required />
          <div class="slot__quick">
            <button type="button" class="slot__chip" @click="setDay(0)">Aujourd'hui</button>
            <button type="button" class="slot__chip" @click="setDay(1)">Demain</button>
          </div>
        </div>
      </div>
      <div class="slot__row">
        <label for="slot-start">Début</label>
        <input id="slot-start" v-model="start" type="time" class="fr-input slot__time" required />
      </div>
      <div class="slot__row">
        <label for="slot-end">Fin</label>
        <div class="slot__control">
          <input id="slot-end" v-model="end" type="time" class="fr-input slot__time" required />
          <div class="slot__quick" role="group" aria-label="Durée">
            <button
              v-for="d in DURATIONS"
              :key="d.minutes"
              type="button"
              class="slot__chip"
              :class="{ 'slot__chip--on': duration === d.minutes }"
              :aria-pressed="duration === d.minutes"
              @click="setDuration(d.minutes)"
            >
              {{ d.label }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- RÉPÉTITION -->
    <section class="slot__group" aria-labelledby="slot-repeat">
      <h3 id="slot-repeat" class="slot__heading">Répétition</h3>
      <div class="slot__row">
        <label for="slot-repeat-select">Répéter</label>
        <select id="slot-repeat-select" v-model="repeat" class="fr-select slot__select">
          <option v-for="o in REPEAT_OPTIONS" :key="o.value" :value="o.value">{{ o.text }}</option>
        </select>
      </div>

      <template v-if="repeat === 'custom'">
        <div class="slot__row">
          <label for="slot-interval">Tous les</label>
          <div class="slot__inline">
            <input id="slot-interval" v-model.number="customInterval" type="number" min="1" class="fr-input slot__number" />
            <select v-model="customUnit" class="fr-select" aria-label="Unité">
              <option v-for="u in UNIT_OPTIONS" :key="u.value" :value="u.value">
                {{ customInterval > 1 ? u.many : u.one }}
              </option>
            </select>
          </div>
        </div>
        <div v-if="customUnit === 'week'" class="slot__row">
          <span id="slot-days-label">Les jours</span>
          <div class="slot__days" role="group" aria-labelledby="slot-days-label">
            <button
              v-for="(initial, i) in WEEKDAY_INITIALS"
              :key="i"
              type="button"
              class="slot__day"
              :class="{ 'slot__day--on': customDays.includes(i) }"
              :aria-pressed="customDays.includes(i)"
              :aria-label="WEEKDAY_NAMES[i]"
              @click="toggleDay(i)"
            >
              {{ initial }}
            </button>
          </div>
        </div>
      </template>

      <template v-if="repeat !== 'none'">
        <div class="slot__row">
          <label for="slot-end-type">Fin de la répétition</label>
          <select id="slot-end-type" v-model="endType" class="fr-select slot__select">
            <option value="never">Jamais</option>
            <option value="until">À une date</option>
            <option value="count">Après un nombre de fois</option>
          </select>
        </div>
        <div v-if="endType === 'until'" class="slot__row">
          <label for="slot-end-date">Jusqu'au</label>
          <input id="slot-end-date" v-model="endDate" type="date" class="fr-input" :min="date" />
        </div>
        <div v-if="endType === 'count'" class="slot__row">
          <label for="slot-end-count">Nombre d'occurrences</label>
          <input id="slot-end-count" v-model.number="endCount" type="number" min="1" class="fr-input slot__number" />
        </div>
      </template>
    </section>

    <!-- RAPPELS -->
    <section class="slot__group" aria-labelledby="slot-reminders">
      <h3 id="slot-reminders" class="slot__heading">Rappels</h3>
      <p v-if="reminderRows.length === 0" class="slot__none">Aucun rappel.</p>
      <div v-for="(r, i) in reminderRows" :key="r.id" class="slot__row">
        <label :for="`slot-rem-${r.id}`">Rappel {{ i + 1 }}</label>
        <div class="slot__inline">
          <select :id="`slot-rem-${r.id}`" v-model="r.preset" class="fr-select">
            <option v-for="p in REMINDER_PRESETS" :key="p.value" :value="String(p.value)">{{ p.text }}</option>
            <option value="custom">Personnalisé…</option>
          </select>
          <template v-if="r.preset === 'custom'">
            <input v-model.number="r.customValue" type="number" min="1" class="fr-input slot__number" aria-label="Durée du rappel" />
            <select v-model="r.customUnit" class="fr-select" aria-label="Unité du rappel">
              <option value="minute">minutes avant</option>
              <option value="hour">heures avant</option>
              <option value="day">jours avant</option>
            </select>
          </template>
          <button type="button" class="slot__remove" :aria-label="`Supprimer le rappel ${i + 1}`" @click="removeReminder(r.id)">
            <VIcon name="ri-close-circle-line" />
          </button>
        </div>
      </div>
      <button
        v-if="reminderRows.length < MAX_REMINDERS"
        type="button"
        class="fr-btn fr-btn--sm fr-btn--tertiary slot__add"
        @click="addReminder"
      >
        <VIcon name="ri-add-line" /> Ajouter un rappel
      </button>
    </section>

    <ul v-if="errors.length" class="slot__errors" role="alert">
      <li v-for="e in errors" :key="e">{{ e }}</li>
    </ul>
  </DsfrModal>
</template>

<style scoped>
.slot__dossier {
  margin: 0;
  font-weight: 700;
}

.slot__summary {
  margin: 0.25rem 0 1rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: var(--background-action-low-blue-france);
  color: var(--text-active-blue-france);
  font-size: 0.875rem;
}

.slot__group {
  margin-bottom: 1rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 0.5rem;
  overflow: hidden;
}

.slot__heading {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background: var(--background-alt-grey);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  color: var(--text-mention-grey);
}

.slot__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.625rem 0.75rem;
  border-top: 1px solid var(--border-default-grey);
}

.slot__row > label,
.slot__row > span {
  flex-shrink: 0;
  font-weight: 500;
}

.slot__control {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.375rem;
}

.slot__inline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.5rem;
}

.slot__time {
  max-width: 8rem;
}

.slot__number {
  max-width: 5.5rem;
}

.slot__select {
  max-width: 16rem;
}

.slot__quick {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.375rem;
}

.slot__chip {
  padding: 0.0625rem 0.625rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 1rem;
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
}

.slot__chip:hover {
  background: var(--background-alt-grey-hover);
}

.slot__chip--on {
  border-color: var(--border-active-blue-france);
  background: var(--background-action-low-blue-france);
  color: var(--text-active-blue-france);
  font-weight: 600;
}

.slot__days {
  display: flex;
  gap: 0.375rem;
}

.slot__day {
  --hover: var(--background-default-grey-hover);
  --active: var(--background-default-grey-active);
  width: 2.25rem;
  height: 2.25rem;
  border: 1px solid var(--border-default-grey);
  border-radius: 50%;
  background: var(--background-default-grey);
  color: var(--text-default-grey);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

.slot__day--on {
  --hover: var(--background-action-high-blue-france-hover);
  --active: var(--background-action-high-blue-france-active);
  border-color: var(--background-action-high-blue-france);
  background: var(--background-action-high-blue-france);
  color: var(--text-inverted-blue-france);
}

.slot__none {
  margin: 0;
  padding: 0.625rem 0.75rem;
  border-top: 1px solid var(--border-default-grey);
  color: var(--text-mention-grey);
}

.slot__remove {
  display: flex;
  padding: 0;
  border: none;
  background: none;
  color: var(--text-default-error);
  font-size: 1.25rem;
  cursor: pointer;
}

.slot__add {
  gap: 0.375rem;
  margin: 0.5rem 0.75rem 0.75rem;
}

.slot__errors {
  margin: 0;
  padding-left: 1.25rem;
  color: var(--text-default-error);
  font-size: 0.875rem;
}

@media (max-width: 36em) {
  .slot__row {
    flex-direction: column;
    align-items: stretch;
  }

  .slot__control,
  .slot__inline,
  .slot__quick {
    align-items: stretch;
    justify-content: flex-start;
  }

  .slot__time,
  .slot__number,
  .slot__select {
    max-width: none;
  }
}
</style>
