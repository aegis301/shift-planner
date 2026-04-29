import { Suspense } from "react";
import { PlanningWorkspace } from "@/components/PlanningWorkspace";

export default function PlanningPage() {
  return (
    <Suspense fallback={null}>
      <PlanningWorkspace />
    </Suspense>
  );
}
