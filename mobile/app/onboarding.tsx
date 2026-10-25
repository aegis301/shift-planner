import { Gate } from "@/components/Gate";
import { OnboardingScreen } from "@/screens/OutcomeScreens";

export default function OnboardingRoute() {
  return (
    <Gate route="/onboarding">
      <OnboardingScreen />
    </Gate>
  );
}
