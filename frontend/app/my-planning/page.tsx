import { Suspense } from "react";
import { PlanningWorkspace } from "@/components/PlanningWorkspace";

export default function MyPlanningPage() {
  return (
    <Suspense fallback={null}>
      <PlanningWorkspace variant="team_member" />
    </Suspense>
  );
}
