import { Suspense } from "react";
import { MemberShell } from "@/components/shell/MemberShell";

export default function MemberLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <MemberShell>{children}</MemberShell>
    </Suspense>
  );
}
