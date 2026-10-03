"use client";

// Renders the Markdown of a guide article from the plain blocks of `parseMarkdown`. Nothing here turns text into
// HTML: every piece is a React element, so an article can never inject markup or script.
import Link from "next/link";
import { useMemo } from "react";

import { parseMarkdown, type Block, type Inline } from "@/lib/guide/markdown-lite";

function InlineRun({ inline }: { inline: readonly Inline[] }) {
  return (
    <>
      {inline.map((part, index) => {
        const key = `${index}-${part.kind}`;
        if (part.kind === "bold") return <strong key={key}>{part.text}</strong>;
        if (part.kind === "italic") return <em key={key}>{part.text}</em>;
        if (part.kind === "code") {
          return (
            <code key={key} className="rounded-field bg-tile px-1 py-0.5 text-small text-ink">
              {part.text}
            </code>
          );
        }
        if (part.kind === "link" && part.href.startsWith("/")) {
          return (
            <Link key={key} href={part.href} className="text-brand-600 underline">
              {part.text}
            </Link>
          );
        }
        if (part.kind === "link") {
          return (
            <a
              key={key}
              href={part.href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 underline"
            >
              {part.text}
            </a>
          );
        }
        return <span key={key}>{part.text}</span>;
      })}
    </>
  );
}

function BlockView({ block }: { block: Block }) {
  if (block.kind === "heading") {
    return block.level === 2 ? (
      <h3 className="mt-7 mb-2.5 text-body-lg font-bold text-heading">{block.text}</h3>
    ) : (
      <h4 className="mt-5 mb-2 text-body font-bold text-heading">{block.text}</h4>
    );
  }
  if (block.kind === "paragraph") {
    return (
      <p className="my-3 text-body leading-[1.85] text-ink">
        <InlineRun inline={block.inline} />
      </p>
    );
  }
  if (block.kind === "quote") {
    return (
      <blockquote className="my-4 rounded-r-card border-l-[3px] border-info bg-info-soft px-5 py-3 text-body leading-[1.85] text-ink">
        <InlineRun inline={block.inline} />
      </blockquote>
    );
  }
  const items = block.items.map((item, index) => (
    <li key={index} className="mb-3 pl-1.5 text-body leading-[1.85] text-ink">
      <InlineRun inline={item} />
    </li>
  ));
  return block.ordered ? (
    <ol className="my-3 list-decimal pl-6">{items}</ol>
  ) : (
    <ul className="my-3 list-disc pl-6">{items}</ul>
  );
}

export function ArticleBody({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown]);
  return (
    <div>
      {blocks.map((block, index) => (
        <BlockView key={index} block={block} />
      ))}
    </div>
  );
}
