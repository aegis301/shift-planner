import { SharedShell } from "@/components/shell/SharedShell";

export default function SharedLayout({ children }: { children: React.ReactNode }) {
  return <SharedShell>{children}</SharedShell>;
}
