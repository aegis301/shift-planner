import { useLocalSearchParams } from "expo-router";
import { Gate } from "@/components/Gate";
import { DutyDetailScreen } from "@/screens/DutyDetailScreen";

export default function DutyRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return (
    <Gate route="/(tabs)">
      <DutyDetailScreen rosterSlotId={Number(id)} />
    </Gate>
  );
}
