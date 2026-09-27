import { Suspense } from "react";
import { MemberPlanning } from "@/components/member/MemberPlanning";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <MemberPlanning />
    </Suspense>
  );
}
