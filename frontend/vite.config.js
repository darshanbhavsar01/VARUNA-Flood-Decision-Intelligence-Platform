import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev calls the deployed API (CORS is open); prod is same-origin (FastAPI serves dist).
export default defineConfig({
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true },
});
