import { Suspense } from "react";
import { HoursLedgerPanel } from "@/components/HoursLedgerPanel";

export default function HoursPage() {
  return (
    <Suspense fallback={null}>
      <HoursLedgerPanel variant="planner" />
    </Suspense>
  );
}
