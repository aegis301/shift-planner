import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        mint: "#3dd6a5",
        coral: "#ff7a70",
        ink: "#16202a",
        cloud: "#f5f8fb",
        surface: "var(--color-surface)",
        "surface-muted": "var(--color-surface-muted)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-text-muted)",
        accent: "var(--color-accent)",
        danger: "var(--color-danger)",
        warning: "var(--color-warning)",
        info: "var(--color-info)",
        "severity-info": "var(--color-severity-info)",
        "severity-warning": "var(--color-severity-warning)",
        "severity-error": "var(--color-severity-error)"
      },
      borderColor: {
        default: "var(--color-border)"
      },
      borderRadius: {
        "token-sm": "var(--radius-sm)",
        "token-md": "var(--radius-md)",
        "token-lg": "var(--radius-lg)"
      },
      fontSize: {
        cell: "var(--font-size-cell)"
      },
      spacing: {
        "cell-x": "var(--space-cell-x)",
        "cell-y": "var(--space-cell-y)"
      },
      boxShadow: {
        soft: "0 18px 60px rgba(22, 32, 42, 0.08)"
      }
    }
  },
  plugins: []
};

export default config;

