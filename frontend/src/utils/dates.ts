export function formatRelativeTime(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return `il y a ${Math.round(hours / 24)} j`;
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

/** Écart en jours calendaires entre une date et aujourd'hui (négatif = passé). */
export function dayOffset(iso: string): number {
  return Math.round((startOfDay(new Date(iso)) - startOfDay(new Date())) / 86_400_000);
}

const dayLabelFormatter = new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "2-digit", month: "long" });

/** « jeudi 05 novembre » : jour de la semaine, jour du mois sur 2 chiffres, mois. */
export function formatDayLabel(date: Date): string {
  return dayLabelFormatter.format(date);
}

/** Titre de groupe d'agenda : « En retard », « Aujourd'hui », « Demain » ou la date. */
export function dayLabel(iso: string): string {
  const offset = dayOffset(iso);
  if (offset < 0) return "En retard";
  if (offset === 0) return "Aujourd'hui";
  if (offset === 1) return "Demain";
  return formatDayLabel(new Date(iso));
}

/** « dans 3 j », « demain », « 2 j de retard »… */
export function formatDue(iso: string): string {
  const offset = dayOffset(iso);
  if (offset === 0) return "aujourd'hui";
  if (offset === 1) return "demain";
  return offset > 0 ? `dans ${offset} j` : `${-offset} j de retard`;
}
