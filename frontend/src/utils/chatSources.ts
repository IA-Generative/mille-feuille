import type { ChatWindowMessage } from "@/components/ChatWindow.vue";
import type { ChatSource } from "@/types/chatSource";

const pageLabel = (numbers: number[]) =>
  numbers.length === 0 ? "" : numbers.length === 1 ? `page ${numbers[0]}` : `pages ${numbers.join(", ")}`;

/**
 * Les sources d'un message sur une seule liste, dans l'ordre de leur numéro (celui que le modèle a cité dans le texte).
 * Un message d'avant la numérotation n'a pas de numéros : ses sources prennent la suite dans l'ordre où elles arrivent,
 * celles du dossier d'abord. `documentName` donne le nom d'un document du dossier.
 */
export function chatSourcesOf(message: ChatWindowMessage, documentName: (documentId: string) => string | undefined): ChatSource[] {
  const items: (Omit<ChatSource, "number"> & { number: number | null })[] = [];

  for (const source of message.sources ?? []) {
    const first = source.pages?.[0];
    items.push({
      number: source.number ?? null,
      key: `dossier-${source.id}`,
      origin: "dossier",
      kind: "document",
      title: (source.dossierDocumentId && documentName(source.dossierDocumentId)) || "Document du dossier",
      pageLabel: pageLabel((source.pages ?? []).map((page) => page.pageNumber)),
      passage: source.excerpt ?? "",
      context: "",
      url: null,
      previewUrl: null,
      boxes: (source.boundingBoxes ?? [])
        .filter((box) => !first || box.pageId === first.id)
        .map((box) => ({ page: first?.pageNumber ?? 1, xMin: box.xMin, yMin: box.yMin, xMax: box.xMax, yMax: box.yMax })),
      dossier: source.dossierDocumentId && first ? { source, documentId: source.dossierDocumentId, pageId: first.id } : null,
    });
  }

  for (const source of message.externalSources ?? []) {
    items.push({
      number: source.number,
      key: `external-${source.sourceId}`,
      origin: "external",
      kind: source.kind,
      title: source.title,
      pageLabel: source.page ? `page ${source.page}` : "",
      passage: source.passage,
      context: source.collectionName,
      url: source.url,
      previewUrl: source.previewUrl,
      boxes: source.boxes,
      dossier: null,
    });
  }

  // Les sources sans numéro (messages d'avant) prennent la suite, sans heurter un numéro déjà pris.
  const taken = new Set(items.map((item) => item.number).filter((n): n is number => n !== null));
  let next = 1;
  const numbered: ChatSource[] = items.map((item) => {
    if (item.number !== null) return { ...item, number: item.number };
    while (taken.has(next)) next++;
    taken.add(next);
    return { ...item, number: next };
  });
  return numbered.sort((a, b) => a.number - b.number);
}

/** Les numéros que le texte peut citer : ceux des sources du message. */
export const citableNumbers = (sources: ChatSource[]) => new Set(sources.map((source) => source.number));

/**
 * Rend chaque `[n]` du texte cliquable quand `n` est le numéro d'une source du message : `[n]` devient un lien
 * `#source-n` que la page intercepte pour placer le carrousel sur la bonne carte. Un `[n]` qui n'est pas une source est
 * laissé tel quel (le modèle ne doit pas inventer de numéro, et on ne fait pas semblant qu'il existe).
 */
export function linkCitations(text: string, numbers: Set<number>): string {
  if (numbers.size === 0) return text;
  return text.replace(/\[(\d{1,3})\](?!\()/g, (match, digits: string) =>
    numbers.has(Number(digits)) ? `[\\[${digits}\\]](#source-${digits})` : match,
  );
}
