import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/network/",
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5174,
    allowedHosts: ["vps-910c1dbc.vps.ovh.net", "213.32.68.67"],
  },
  preview: {
    host: "0.0.0.0",
    port: 5174,
    allowedHosts: ["vps-910c1dbc.vps.ovh.net", "213.32.68.67"],
  },
  resolve: {
    alias: {
      process: "process/browser",
      buffer: "buffer",
    },
  },
  define: {
    global: "globalThis",
    "process.env": {},
  },
  optimizeDeps: {
    include: ["buffer", "process", "@solana/web3.js", "@coral-xyz/anchor"],
  },
});
