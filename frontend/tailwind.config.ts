import type { Config } from "tailwindcss";

export default {
  darkMode: ["class"],
  content: [
    "./client/src/**/*.{ts,tsx}",
    "./client/index.html",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      colors: {
        bg: "#060912",
        surface: "#0d1117",
        "surface-2": "#111827",
        "surface-offset": "#161d2e",
        card: "#0f1623",
        border: "#243048",
        divider: "#1e2d45",
        text: {
          DEFAULT: "#e2e8f0",
          muted: "#94a3b8",
          faint: "#475569",
        },
        purple: {
          DEFAULT: "#7c3aed",
          hover: "#6d28d9",
        },
        teal: {
          DEFAULT: "#38bdf8",
          hover: "#0ea5e9",
        },
        violet: {
          DEFAULT: "#818cf8",
          hover: "#6366f1",
        },
        green: {
          DEFAULT: "#10b981",
          hover: "#059669",
        },
        amber: {
          DEFAULT: "#f59e0b",
          hover: "#d97706",
        },
        red: {
          DEFAULT: "#f87171",
          hover: "#ef4444",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "1rem",
        "2xl": "1.5rem",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        fadeIn: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-glow": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        fadeIn: "fadeIn 0.4s ease forwards",
        slideIn: "slideIn 0.3s ease forwards",
        "pulse-glow": "pulse-glow 1.5s ease-in-out infinite",
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, #7c3aed 0%, #818cf8 50%, #38bdf8 100%)",
        "gradient-card": "linear-gradient(135deg, #0f1623 0%, #161d2e 100%)",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
} satisfies Config;
