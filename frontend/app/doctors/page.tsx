import { LocaleShell } from "@/components/LocaleProvider";
import { DoctorForm } from "@/components/ResourceForms";

export default function DoctorsPage() {
  return (
    <LocaleShell>
      <DoctorForm />
    </LocaleShell>
  );
}

