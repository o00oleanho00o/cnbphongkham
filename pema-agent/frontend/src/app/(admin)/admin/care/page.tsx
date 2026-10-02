import { redirect } from "next/navigation";

/** `/admin/care` opens the first tab. */
export default function AdminCareIndex() {
  redirect("/admin/care/staff");
}
