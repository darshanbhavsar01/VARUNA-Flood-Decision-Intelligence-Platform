/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 900: "#0a1018", 800: "#0f1723", 700: "#16202e", 600: "#1d2a3a" },
        risk: { high: "#ef4444", moderate: "#f59e0b", low: "#22c55e", unknown: "#475569" },
        accent: { DEFAULT: "#4fc3f7", soft: "#7ee787" },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
    },
  },
  plugins: [],
};
