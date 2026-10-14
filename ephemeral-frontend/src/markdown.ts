/**
 * Rendu Markdown minimaliste — sans dépendance externe.
 *
 * Suffit pour le CHANGELOG et les CGU de MilleFeuille : titres, listes,
 * gras, liens, code inline, paragraphes. Le HTML produit est échappé en
 * amont pour éviter toute injection XSS (les contenus viennent de fichiers
 * statiques servis par l'app elle-même, mais on reste prudent).
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInline(text: string): string {
  let out = escapeHtml(text);
  // Liens [label](url) — on n'autorise que http(s)
  out = out.replace(
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  // Code inline `code`
  out = out.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Gras **text**
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return out;
}

export function renderMarkdown(md: string): string {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inList = false;
  let inCode = false;
  let codeBuffer: string[] = [];

  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };

  for (const raw of lines) {
    const line = raw;

    // Bloc de code ```
    if (line.trim().startsWith("```")) {
      if (inCode) {
        html.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
        codeBuffer = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }

    // Titres
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      closeList();
      const level = h[1].length;
      html.push(`<h${level}>${renderInline(h[2])}</h${level}>`);
      continue;
    }

    // Ligne de séparation ---
    if (/^---\s*$/.test(line)) {
      closeList();
      html.push("<hr />");
      continue;
    }

    // Éléments de liste - ou *
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (li) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${renderInline(li[1])}</li>`);
      continue;
    }

    // Ligne vide
    if (line.trim() === "") {
      closeList();
      continue;
    }

    // Paragraphe
    closeList();
    html.push(`<p>${renderInline(line)}</p>`);
  }

  closeList();
  if (inCode) {
    html.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
  }

  return html.join("\n");
}
