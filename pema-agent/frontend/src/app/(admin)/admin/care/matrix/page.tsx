"use client";

// Ma trận ngưỡng độ sâu và mức tự chủ, kèm nhãn "chờ bác sĩ duyệt". CSKH không thấy trang này.
import { useCallback } from "react";

import { MatrixEditor } from "@/components/care/matrix-editor";
import { NoAccess } from "@/components/care/care-ui";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { careApi } from "@/lib/care/care-api";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

export default function CareMatrixPage() {
  const { can } = useSession();
  if (!can("care.matrix")) return <NoAccess what="xem ma trận ngưỡng" />;
  return <MatrixContent />;
}

function MatrixContent() {
  const load = useCallback((signal: AbortSignal) => careApi.matrix(signal), []);
  const { data, error, loading, reload } = useLoad(load);
  return (
    <div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {/* a new version remounts the editor, so its fields start from what the backend now holds */}
      {data && <MatrixEditor key={data.version} matrix={data} onChanged={reload} />}
    </div>
  );
}
