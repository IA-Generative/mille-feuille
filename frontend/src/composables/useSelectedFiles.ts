import { ref } from "vue";

// Même règle que l'attribut `accept` du champ de dépôt (".pdf,image/*"), que le glisser-déposer n'applique pas.
const isAccepted = (file: File) => file.type === "application/pdf" || file.type.startsWith("image/") || /\.pdf$/i.test(file.name);
const s = (n: number) => (n > 1 ? "s" : "");

/**
 * Fichiers choisis avant l'envoi (création d'un dossier, ajout de documents) : liste, refus des types non acceptés
 * et messages. `message` est un résumé à afficher sous le champ de dépôt dans un `role="status"` (visible et annoncé) ;
 * `error` va dans la prop `error` du champ de dépôt.
 */
export function useSelectedFiles() {
  const files = ref<File[]>([]);
  const message = ref("");
  const error = ref("");

  function reset(initial: File[] = []) {
    files.value = [...initial];
    message.value = "";
    error.value = "";
  }

  function add(fileList: FileList | File[]) {
    const incoming = Array.from(fileList);
    const accepted = incoming.filter(isAccepted);
    const refused = incoming.filter((file) => !isAccepted(file));
    files.value.push(...accepted);
    error.value = refused.length
      ? `${refused.length} fichier${s(refused.length)} refusé${s(refused.length)} : ${refused.map((file) => file.name).join(", ")}. Seuls les PDF et les images sont acceptés.`
      : "";
    message.value = accepted.length
      ? `${accepted.length} fichier${s(accepted.length)} ajouté${s(accepted.length)}, ${files.value.length} au total.`
      : "Aucun fichier ajouté.";
  }

  function remove(index: number) {
    const [removed] = files.value.splice(index, 1);
    error.value = "";
    message.value = files.value.length
      ? `Fichier ${removed?.name} retiré, ${files.value.length} au total.`
      : `Fichier ${removed?.name} retiré, plus aucun fichier.`;
  }

  return { files, message, error, reset, add, remove };
}
