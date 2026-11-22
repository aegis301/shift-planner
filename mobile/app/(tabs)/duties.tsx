import { useRouter } from "expo-router";
import { DutiesScreen } from "@/screens/DutiesScreen";

export default function DutiesRoute() {
  const router = useRouter();
  return <DutiesScreen onOpenDuty={(id, date) => router.push({ pathname: "/duty/[id]", params: { id: String(id), date } })} />;
}
