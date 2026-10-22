/** Une page de résultats telle que l'API la renvoie. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
