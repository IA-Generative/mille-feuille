// Mêmes règles que le job lint-commits de la CI (dnum-mi/fabnum-cicd lint-commits.yml : @commitlint/config-conventional
// 19.8.1 + types limités + sujet de 100 caractères au plus), pour les attraper dès le commit via le hook
// pre-commit `commitlint`. Les règles sont écrites ici plutôt qu'héritées (`extends`) : depuis ce dossier, le hook ne
// retrouverait pas le paquet config-conventional. Si la CI change ses règles, mettre ce fichier à jour.
export default {
  rules: {
    "body-leading-blank": [1, "always"],
    "body-max-line-length": [2, "always", 100],
    "footer-leading-blank": [1, "always"],
    "footer-max-line-length": [2, "always", 100],
    "header-max-length": [2, "always", 100],
    "header-trim": [2, "always"],
    "subject-case": [2, "never", ["sentence-case", "start-case", "pascal-case", "upper-case"]],
    "subject-empty": [2, "never"],
    "subject-full-stop": [2, "never", "."],
    "type-case": [2, "always", "lower-case"],
    "type-empty": [2, "never"],
    "type-enum": [2, "always", ["feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert"]],
  },
};
