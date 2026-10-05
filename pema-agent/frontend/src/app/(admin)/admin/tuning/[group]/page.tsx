// ported from: web/src/pages/tuning-page.tsx (route `/tuning/:nhom`)
//
// The group lives in the URL so a link can open it directly (the "LLM not configured" banner of the
// overview points at /admin/tuning/providers). The page component reads `group` from `useParams`.
import TuningPage from "../page";

export default TuningPage;
