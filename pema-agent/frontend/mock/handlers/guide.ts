// Mock of the staff guide and "Hỏi Pema": the articles are the rows of `clinic.guide_article`, kept here in memory
// from the seeds. The real backend ranks passages with full-text search; here a passage scores by how many question
// words it contains (diacritics ignored), which is enough to look at the screens. Not a second implementation.
import { GUIDE_SEEDS } from "../data/guide";
import { DAY, bodyOf, fail, isoFromNow, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

const GUIDE = "guide";
const ASK_HITS = 5;

type Article = { id: string; title: string; body: string; tags: string[]; updated_at: string };

const articles = new Map<string, Article>(
  GUIDE_SEEDS.map((g) => [
    g.id,
    {
      id: g.id,
      title: g.name,
      body: g.body,
      tags: [GUIDE, g.topic],
      updated_at: isoFromNow(-3 * DAY),
    },
  ]),
);

const fold = (text: string): string =>
  text.replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const FILLER = new Set("la va cua the nao gi khi nhu co khong de cho toi minh lam sao".split(" "));

function summaryOf(body: string): string {
  const paragraph = body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .find((p) => p !== "" && !p.startsWith("#"));
  const plain = (paragraph ?? "").replace(/\*\*|`/g, "").replace(/\s+/g, " ");
  return plain.length <= 240 ? plain : `${plain.slice(0, 239).trimEnd()}…`;
}

function isArticle(id: string): boolean {
  return (articles.get(id)?.tags ?? []).includes(GUIDE);
}

function summaryRow(id: string): S["GuideArticleSummary"] {
  const article = articles.get(id);
  if (!article) fail(404, "not_found", "Không tìm thấy bài hướng dẫn.");
  return {
    id,
    title: article.title,
    topic: article.tags.find((t) => t !== GUIDE) ?? "",
    tags: article.tags,
    summary: summaryOf(article.body),
    status: "san_sang",
    updated_at: article.updated_at,
  };
}

type Passage = { articleId: string; title: string; heading: string; text: string };

function passagesOf(id: string): Passage[] {
  const title = articles.get(id)?.title ?? "";
  const sections = (articles.get(id)?.body ?? "").split(/\n(?=#{1,6}\s)/).map((block) => {
    const [first = "", ...rest] = block.split("\n");
    const isHeading = /^#{1,6}\s/.test(first);
    return {
      heading: isHeading ? first.replace(/^#{1,6}\s+/, "") : "",
      text: (isHeading ? rest : [first, ...rest]).join("\n").trim(),
    };
  });
  return sections
    .filter((s) => s.text !== "")
    .map((s) => ({ articleId: id, title, heading: s.heading, text: s.text.slice(0, 700) }));
}

export function register(r: Router): void {
  r.get("/api/v1/guide/articles", "kb.read", (): Reply => ({
    body: [...articles.keys()]
      .filter(isArticle)
      .map(summaryRow)
      .toSorted((a, b) => a.title.localeCompare(b.title, "vi")),
  }));

  r.get("/api/v1/guide/articles/{article_id}", "kb.read", (ctx): Reply => {
    const id = ctx.params.article_id ?? "";
    if (!isArticle(id)) fail(404, "not_found", "Không tìm thấy bài hướng dẫn.");
    return { body: { ...summaryRow(id), body: articles.get(id)?.body ?? "" } };
  });

  r.put("/api/v1/guide/articles/{article_id}/tags", "kb.manage", (ctx): Reply => {
    const id = ctx.params.article_id ?? "";
    const article = articles.get(id);
    if (!article) fail(404, "not_found", "Không tìm thấy bài hướng dẫn.");
    const { tags } = bodyOf<S["GuideTagsUpdate"]>(ctx);
    if (tags.some((t) => t.trim() === ""))
      fail(422, "validation_failed", "Nhãn không được để trống.");
    const cleaned = [...new Set(tags.map((t) => t.trim()))].map((t) =>
      t.toLowerCase() === GUIDE ? GUIDE : t,
    );
    if (cleaned.length > 10) fail(422, "validation_failed", "Tối đa 10 nhãn cho một bài.");
    article.tags = cleaned;
    return { body: summaryRow(id) };
  });

  r.post("/api/v1/guide/ask", "kb.read", (ctx): Reply => {
    const { question } = bodyOf<S["GuideAskRequest"]>(ctx);
    if (question.trim() === "") fail(422, "validation_failed", "Nhập câu hỏi.");
    const words = fold(question)
      .split(/[^a-z0-9]+/)
      .filter((w) => w.length > 1 && !FILLER.has(w));
    const hits: S["GuideAskHit"][] = [...articles.keys()]
      .filter(isArticle)
      .flatMap(passagesOf)
      .map((p) => {
        const haystack = fold(`${p.title} ${p.heading} ${p.text}`);
        return { p, score: words.filter((w) => haystack.includes(w)).length };
      })
      .filter((m) => m.score > 0)
      .toSorted((a, b) => b.score - a.score)
      .slice(0, ASK_HITS)
      .map(({ p, score }) => ({
        article_id: p.articleId,
        article_title: p.title,
        heading: p.heading,
        passage: p.text,
        score,
      }));
    return { body: { hits } };
  });
}
