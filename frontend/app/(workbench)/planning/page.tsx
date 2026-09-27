import { Suspense } from "react";
import { PlannerWorkspace } from "@/components/planning/PlannerWorkspace";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <PlannerWorkspace />
    </Suspense>
  );
}
