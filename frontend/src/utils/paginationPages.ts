/**
 * Les pages à donner à `DsfrPagination`. Le `href` est indispensable : sans lui, le DSFR rend le lien « inactif »
 * (curseur interdit, couleur de lien désactivé) et il sort de l'ordre de tabulation. La bibliothèque intercepte le clic
 * (`@click.prevent`), donc `"#"` ne fait pas naviguer.
 */

export function paginationPages(pageCount: number) {
    return Array.from({ length: Math.max(1, pageCount) }, (_, i) => ({
        label: String(i + 1),
        title: `Page ${i + 1}`,
        href: "#",
    }));
}