import { nextTick, watch, type Ref } from "vue";

/** À l'ouverture d'une fenêtre maison, le focus y entre ; à la fermeture, il revient sur le bouton qui l'a ouverte. */
export function useDialogFocus(open: Ref<boolean>, dialog: Ref<HTMLElement | null>){
    let opener: HTMLElement | null = null;
    watch(open, async(isOpen) => {
        if(isOpen) {
            opener = document.activeElement as HTMLElement | null;
            await nextTick();
            dialog.value?.focus();
        } else {
            opener?.focus();
            opener = null;
        }
    });
}