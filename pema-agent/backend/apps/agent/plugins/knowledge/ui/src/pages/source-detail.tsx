import { ui } from "../sdk";

export function SourceDetail({ id, onBack }: { id: string; onBack: () => void }) {
  return (
    <div>
      <ui.Button variant="secondary" onClick={onBack}>
        Về danh sách
      </ui.Button>
      <ui.PageHeader title={id} />
    </div>
  );
}
