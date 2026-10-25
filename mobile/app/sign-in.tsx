import { Gate } from "@/components/Gate";
import { SignInScreen } from "@/screens/SignInScreen";

export default function SignInRoute() {
  return (
    <Gate route="/sign-in">
      <SignInScreen />
    </Gate>
  );
}
