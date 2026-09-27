import { WorkbenchShell } from "@/components/shell/WorkbenchShell";

export default function WorkbenchLayout({ children }: { children: React.ReactNode }) {
  return <WorkbenchShell>{children}</WorkbenchShell>;
}
