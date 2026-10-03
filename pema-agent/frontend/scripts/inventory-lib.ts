// Checks behind `pnpm inventory` (package U, step U1): plain functions over text, so `src/lib/inventory.test.ts`
// can run them on small inputs. The command itself is `inventory-check.ts`.
//
// `pnpm inventory` fails (exit 1, one line per problem) when
//   - a route of the first table has no `src/app/**/page.tsx`, or a page has no row;
//   - a test id of the file no longer exists: the file is gone, or the `::title` is not the title of an
//     `it`, `test` or `describe` in it;
//   - a test file under `src/` or `mock/` is not named anywhere in the inventory.

export type Problems = string[];
export type TestId = { file: string; title: string | null };

/** Rows of the route table: the route in backticks at the start of the row. */
export function routeRows(markdown: string): { route: string }[] {
  return markdown
    .split("\n")
    .map((line) => /^\| `(\/[^`]*)`/.exec(line)?.[1])
    .filter((route): route is string => route !== undefined)
    .map((route) => ({ route }));
}

/** Every `file` or `file::title` token in backticks that points at a test file. */
export function testIds(markdown: string): TestId[] {
  return [...markdown.matchAll(/`([^`]+?\.test\.tsx?)(?:::([^`]+))?`/g)].flatMap((match) =>
    match[1] === undefined ? [] : [{ file: match[1], title: match[2] ?? null }],
  );
}

/** True when `title` is the title (or a part of it) of an `it`, `test` or `describe` call in `source`. */
export function hasTestTitle(source: string, title: string): boolean {
  const calls = source.matchAll(/\b(?:it|test|describe)(?:\.\w+)*\(\s*(["'`])((?:\.|(?!\1).)*)\1/g);
  return [...calls].some((call) => (call[2] ?? "").includes(title));
}

export function checkRoutes(rows: { route: string }[], pageRoutes: readonly string[]): Problems {
  const listed = new Set(rows.map((r) => r.route));
  const existing = new Set(pageRoutes);
  return [
    ...rows.filter((r) => !existing.has(r.route)).map((r) => `route ${r.route} has no page.tsx`),
    ...pageRoutes.filter((r) => !listed.has(r)).map((r) => `page ${r} has no row in the inventory`),
  ];
}

function problemOfTestId({ file, title }: TestId, source: string | null): Problems {
  if (source === null) return [`test file ${file} does not exist`];
  if (title === null || hasTestTitle(source, title)) return [];
  return [`test "${title}" is not in ${file}`];
}

export function checkTestIds(
  ids: readonly TestId[],
  read: (file: string) => string | null,
): Problems {
  return ids.flatMap((id) => problemOfTestId(id, read(id.file)));
}

export function checkAllTestFilesListed(
  ids: readonly { file: string }[],
  testFiles: readonly string[],
): Problems {
  const listed = new Set(ids.map((i) => i.file));
  return testFiles
    .filter((f) => !listed.has(f))
    .map((f) => `test file ${f} is not named in the inventory`);
}
