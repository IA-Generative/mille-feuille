import { onBeforeUnmount, onMounted, type Ref } from "vue";

type MaybeElement = Ref<HTMLElement | null | undefined>;

/**
 * Appelle `onOutside` sur un clic extérieur à `roots`, à condition que l'appui ait lui aussi eu lieu à l'extérieur :
 * une sélection de texte qui part d'un champ du menu et finit dehors ne doit pas le fermer (le `click` est alors
 * envoyé à l'ancêtre commun, donc « dehors »). Un clic sans appui (clavier) n'est jugé que sur sa cible.
 * `roots` : un élément, ou plusieurs (ex. un bouton et sa liste placée ailleurs dans le DOM).
 */
export function useOutsideClick(roots: MaybeElement | MaybeElement[], onOutside: () => void) {
  const list = Array.isArray(roots) ? roots : [roots];
  // null : pas d'appui connu (clic au clavier).
  let pressedOutside: boolean | null = null;

  const isOutside = (target: EventTarget | null) => {
    const elements = list.map((root) => root.value).filter((el): el is HTMLElement => !!el);
    return elements.length > 0 && !elements.some((el) => el.contains(target as Node));
  };

  const onPointerdown = (event: PointerEvent) => {
    pressedOutside = isOutside(event.target);
  };
  const onClick = (event: MouseEvent) => {
    const startedOutside = pressedOutside ?? true;
    pressedOutside = null;
    if (startedOutside && isOutside(event.target)) onOutside();
  };

  onMounted(() => {
    document.addEventListener("pointerdown", onPointerdown, true);
    document.addEventListener("click", onClick);
  });
  onBeforeUnmount(() => {
    document.removeEventListener("pointerdown", onPointerdown, true);
    document.removeEventListener("click", onClick);
  });
}
