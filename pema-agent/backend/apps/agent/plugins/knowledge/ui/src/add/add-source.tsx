import { Sheet } from "../parts";

/** The three-step flow that adds sources. `initial` fills the "type text" way (a question with no document). */
export function AddSourceSheet({
  onClose,
}: {
  onClose: () => void;
  onAdded: (count: number) => void;
  initial?: { title: string; text: string };
}) {
  return (
    <Sheet title="Thêm nguồn" onClose={onClose} wide>
      <p>Chưa dựng</p>
    </Sheet>
  );
}
