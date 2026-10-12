/** Step 3 "Xem trước": what the reader made of each file, before anything is added. */
import { AUDIENCE_LABEL, AUDIENCE_SPLIT, WARNING_TONE, formatSize, periodText } from "../logic";
import { Section } from "../parts";
import { ui } from "../sdk";
import type { OutlineNode, PreviewWarning } from "../types";
import { type CodeGroup, type Entry, groupByCode, refusalOf, summaryText } from "./add-logic";
import type { AddFlow } from "./use-add-flow";

function Outline({ nodes }: { nodes: OutlineNode[] }) {
  if (nodes.length === 0) return <p className="text-label text-ink-soft">Chưa dựng được cây tiêu đề.</p>;
  return (
    <ul aria-label="Cây tiêu đề" className="space-y-0.5">
      {nodes.map((node, index) => (
        <li
          key={`${index}-${node.title}`}
          style={{ paddingLeft: `${(node.level - 1) * 16}px` }}
          className="flex items-baseline justify-between gap-3 text-small text-ink"
        >
          <span className={`min-w-0 break-words ${node.level === 1 ? "font-bold" : ""}`}>{node.title}</span>
          <span className="shrink-0 text-label text-ink-soft">{node.chunks} đoạn</span>
        </li>
      ))}
    </ul>
  );
}

function Warning({ warning }: { warning: PreviewWarning }) {
  return (
    <ui.Notice tone={WARNING_TONE[warning.level]}>
      <span className="block">{warning.text}</span>
      {warning.fix && <span className="mt-0.5 block text-label">Cách xử lý: {warning.fix}</span>}
    </ui.Notice>
  );
}

function Facts({ entry }: { entry: Entry }) {
  const { item } = entry;
  return (
    <dl className="grid grid-cols-3 gap-2 text-center">
      {[
        ["Đoạn", String(item.chunk_count)],
        ["Dài trung bình", `${item.avg_chars} ký tự`],
        ["Bảng tách hàng", String(item.tables_split)],
      ].map(([label, value]) => (
        <div key={label} className="rounded-tile border border-line px-2 py-1.5">
          <dt className="text-micro text-ink-soft">{label}</dt>
          <dd className="text-small font-bold text-heading">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Card({ entry, benchmark }: { entry: Entry; benchmark: boolean }) {
  const { item, draft } = entry;
  const refusal = refusalOf(item, benchmark);
  const skipped = draft.action === "skip";
  return (
    <div className={`space-y-3 rounded-tile border border-line p-4 ${refusal || skipped ? "opacity-80" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-small font-bold break-words text-heading">{draft.title || item.name}</p>
          <p className="text-label text-ink-soft">
            {item.name} · {formatSize(item.size)}
            {draft.version ? ` · v${draft.version}` : ""}
          </p>
        </div>
        {refusal && <ui.Badge tone="danger">Không nạp</ui.Badge>}
        {!refusal && skipped && <ui.Badge tone="warning">Bỏ qua</ui.Badge>}
        {AUDIENCE_SPLIT && !refusal && !skipped && <ui.Badge tone={draft.audience === "patient" ? "info" : "neutral"}>{AUDIENCE_LABEL[draft.audience]}</ui.Badge>}
      </div>
      {refusal && <ui.Notice tone="danger">{refusal}</ui.Notice>}
      {!refusal && skipped && item.same_content_as && (
        <ui.Notice tone="warning">Trùng hệt với nguồn "{item.same_content_as.title}": tệp này được bỏ qua.</ui.Notice>
      )}
      {!refusal && skipped && !item.same_content_as && <ui.Notice tone="warning">Tệp này được bỏ qua theo lựa chọn ở bước Thông tin.</ui.Notice>}
      {!refusal && !skipped && item.same_code_as && (
        <ui.Notice tone="info">
          Cùng mã với "{item.same_code_as.title}": sẽ thêm như phiên bản mới, nguồn cũ giữ lịch sử.
        </ui.Notice>
      )}
      {!refusal && (
        <>
          <p className="text-label text-ink-soft">Hiệu lực: {periodText(draft.from || null, draft.to || null)}</p>
          <Facts entry={entry} />
          <Outline nodes={item.outline} />
          {item.warnings.filter((warning) => AUDIENCE_SPLIT || warning.code !== "internal_script").map((warning) => (
            <Warning key={`${warning.code}-${warning.text}`} warning={warning} />
          ))}
        </>
      )}
    </div>
  );
}

function Group({ group, benchmark }: { group: CodeGroup; benchmark: boolean }) {
  const cards = group.entries.map((entry) => <Card key={entry.item.key} entry={entry} benchmark={benchmark} />);
  if (group.code === null) return <>{cards}</>;
  return (
    <Section title={`Mã ${group.code}: ${group.entries.length} phiên bản cạnh nhau`}>
      <div className="grid gap-3 lg:grid-cols-2">{cards}</div>
    </Section>
  );
}

export function PreviewStep({ flow }: { flow: AddFlow }) {
  const groups = groupByCode(flow.entries);
  return (
    <div className="space-y-4">
      <ui.Notice tone="info">{summaryText(flow.summary)}. Chưa có gì được nạp; máy mới đọc thử, chưa tốn tiền model.</ui.Notice>
      {groups.map((group) => (
        <Group key={group.code ?? group.entries[0]?.item.key} group={group} benchmark={flow.benchmark} />
      ))}
    </div>
  );
}
