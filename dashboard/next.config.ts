import type { NextConfig } from "next";

// Static export: `npm run build` produces plain HTML/CSS/JS in `out/`,
// which can be served by any web server (or the backend container).
const nextConfig: NextConfig = {
  output: "export",
  // Allow opening the dev server from other devices on the local network
  // (e.g. a phone or a teammate's laptop). Only affects `npm run dev`.
  allowedDevOrigins: ["192.168.56.*", "192.168.1.*", "192.168.0.*"],
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
