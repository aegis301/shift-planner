import { Suspense } from "react";
import { MemberHome } from "@/components/member/MemberHome";

export default function Page() {
  return (
    <Suspense fallback={null}>
      <MemberHome />
    </Suspense>
  );
}
