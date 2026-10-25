import { useLocalSearchParams } from "expo-router";
import { Gate } from "@/components/Gate";
import { DutyDetailScreen } from "@/screens/DutyDetailScreen";

export default function DutyRoute() {
  const { id, date } = useLocalSearchParams<{ id: string; date?: string }>();
  const slotDate = Array.isArray(date) ? date[0] : date;
  return (
    <Gate route="/(tabs)">
      <DutyDetailScreen rosterSlotId={Number(id)} slotDate={slotDate} />
    </Gate>
  );
}
