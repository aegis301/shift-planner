import { Suspense } from "react";
import { HoursLedgerPanel } from "@/components/HoursLedgerPanel";

export default function MyHoursPage() {
  return (
    <Suspense fallback={null}>
      <HoursLedgerPanel variant="member" />
    </Suspense>
  );
}
