import { useRouter } from "expo-router";
import { HomeScreen } from "@/screens/HomeScreen";

export default function HomeRoute() {
  const router = useRouter();
  return <HomeScreen onOpenDuty={(id, date) => router.push({ pathname: "/duty/[id]", params: { id: String(id), date } })} />;
}
