import { Gate } from "@/components/Gate";
import { NoMemberScreen } from "@/screens/OutcomeScreens";

export default function NoMemberRoute() {
  return (
    <Gate route="/no-member">
      <NoMemberScreen />
    </Gate>
  );
}
