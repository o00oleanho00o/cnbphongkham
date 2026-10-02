import { redirect } from "next/navigation";

/** `/care/patients/<id>` opens the timeline. */
export default async function PatientCareIndex({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/care/patients/${encodeURIComponent(id)}/timeline`);
}
