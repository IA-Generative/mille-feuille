/**
 * Règle de fermeture au clic sur le fond d'une fenêtre : il faut que l'appui ET le relâchement aient eu lieu
 * sur le fond. Le navigateur envoie le `click` à l'ancêtre commun des deux endroits : sans cette règle, une
 * sélection de texte, un redimensionnement ou un défilement qui finit dehors est pris pour un clic sur le fond.
 *
 * `isBackdrop` dit si l'événement vise le fond ; il est appelé de façon synchrone (`currentTarget` y est valide).
 */
export function useBackdropClose(isBackdrop: (event: Event) => boolean, onClose: () => void) {
    let pressed = false;
    let released = false;

    return {
        onPointerdown(event: PointerEvent) {
            pressed = isBackdrop(event);
            released = false;
        },
        onPointerup(event: PointerEvent) {
            released = isBackdrop(event);
        },
        onClick(event: MouseEvent) {
            const shouldClose = pressed && released && isBackdrop(event);
            pressed = released = false;
            if (shouldClose) onClose()
        },
    };
}