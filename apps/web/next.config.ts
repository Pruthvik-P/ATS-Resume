import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Emit a self-contained server (`.next/standalone`) for the Docker image.
  // `next start` still works locally; this only adds the standalone copy.
  output: "standalone",
};

export default nextConfig;
