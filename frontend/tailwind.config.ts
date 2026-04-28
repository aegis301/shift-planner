import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        mint: "#3dd6a5",
        coral: "#ff7a70",
        ink: "#16202a",
        cloud: "#f5f8fb"
      },
      boxShadow: {
        soft: "0 18px 60px rgba(22, 32, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;

