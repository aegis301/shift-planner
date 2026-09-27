import { redirect } from "next/navigation";

export default function OrganizationRedirectPage() {
  redirect("/organization/team/requests");
}
