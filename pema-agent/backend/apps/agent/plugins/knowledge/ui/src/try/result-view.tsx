/** What a search trial found: the folded question, the services it recognised, the total time, then every stage. */
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { SearchDebug } from "../types";
import { StageCard } from "./stage-card";
import { formatMs } from "./try-logic";

export function ResultView({ result, onOpenSource }: { result: SearchDebug; onOpenSource: (sourceId: string) => void }) {
  return (
    <div className="space-y-3">
      <ui.Card title="Kết quả" aside={<span className="text-small text-ink-soft">Tổng {formatMs(result.total_ms)}</span>}>
        <dl className="space-y-2 text-small">
          <div>
            <dt className="text-label text-ink-soft">Câu hỏi đã bỏ dấu</dt>
            <dd className="break-words text-ink">{result.folded || "(trống)"}</dd>
          </div>
          <div>
            <dt className="mb-1 text-label text-ink-soft">Dịch vụ nhận ra</dt>
            <dd className="flex flex-wrap gap-1.5">
              {result.services.length === 0 ? (
                <span className="text-ink-soft">Không nhận ra dịch vụ nào</span>
              ) : (
                result.services.map((service) => <Chip key={service}>{service}</Chip>)
              )}
            </dd>
          </div>
        </dl>
      </ui.Card>
      {result.stages.map((stage) => (
        <StageCard key={stage.id} stage={stage} onOpenSource={onOpenSource} />
      ))}
    </div>
  );
}
