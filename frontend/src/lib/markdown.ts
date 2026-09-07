const FRONTMATTER_PATTERN = /^---[\t ]*\r?\n[\s\S]*?\r?\n---[\t ]*(?:\r?\n|$)/;

export interface MarkdownDocument {
  frontmatter: string;
  body: string;
}

export function splitMarkdownDocument(content: string): MarkdownDocument {
  const match = content.match(FRONTMATTER_PATTERN);
  if (!match) return { frontmatter: "", body: content };

  return {
    frontmatter: match[0].trimEnd(),
    body: content.slice(match[0].length).trimStart(),
  };
}

export function joinMarkdownDocument(frontmatter: string, body: string): string {
  return frontmatter ? `${frontmatter}\n${body}` : body;
}

export function stripMarkdownFrontmatter(content: string): string {
  return splitMarkdownDocument(content).body;
}
