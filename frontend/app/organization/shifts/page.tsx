import { redirect } from "next/navigation";

export default function ShiftManagementIndexPage() {
  redirect("/organization/shifts/groups");
}
