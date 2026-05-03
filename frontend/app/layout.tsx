import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ClientRoot } from "./ClientRoot";

export const metadata: Metadata = {
  title: "Shift Planner",
  description: "AI-first shift planning for healthcare teams",
  manifest: "/manifest.json"
};

export const viewport: Viewport = {
  themeColor: "#3dd6a5",
  width: "device-width",
  initialScale: 1
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="de">
      <body>
        <ClientRoot>{children}</ClientRoot>
      </body>
    </html>
  );
}

