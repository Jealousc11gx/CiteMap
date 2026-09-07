import { describe, expect, it } from "vitest";
import {
  joinMarkdownDocument,
  splitMarkdownDocument,
  stripMarkdownFrontmatter,
} from "./markdown";

describe("stripMarkdownFrontmatter", () => {
  it("removes YAML frontmatter from a note preview", () => {
    const content = "---\ntitle: Test\nauthors: [Ada]\n---\n# Heading\n\nBody";

    expect(stripMarkdownFrontmatter(content)).toBe("# Heading\n\nBody");
  });

  it("supports CRLF line endings", () => {
    const content = "---\r\ntitle: Test\r\n---\r\nParagraph";

    expect(stripMarkdownFrontmatter(content)).toBe("Paragraph");
  });

  it("keeps content without a complete frontmatter block", () => {
    const content = "---\nunfinished metadata\n# Heading";

    expect(stripMarkdownFrontmatter(content)).toBe(content);
  });

  it("separates frontmatter from the editable body and restores it on save", () => {
    const content = "---\ntitle: Test\nauthors: [Ada]\n---\n# Heading\n\nReadable body";

    const document = splitMarkdownDocument(content);

    expect(document.frontmatter).toBe("---\ntitle: Test\nauthors: [Ada]\n---");
    expect(document.body).toBe("# Heading\n\nReadable body");
    expect(joinMarkdownDocument(document.frontmatter, document.body)).toBe(content);
  });

  it("leaves plain Markdown unchanged when saving", () => {
    const document = splitMarkdownDocument("# Personal note");

    expect(document.frontmatter).toBe("");
    expect(joinMarkdownDocument(document.frontmatter, document.body)).toBe("# Personal note");
  });
});
