import type { NextConfig } from "next";

// Il rewrite Next.js (`/api/*` → backend) è stato rimosso: con la rete
// `dokploy-network` external (Docker Swarm overlay) il DNS service-discovery
// non è affidabile dal frontend. Le chiamate API vanno fatte direttamente
// dal browser a `NEXT_PUBLIC_BACKEND_URL` (CORS gestito lato FastAPI).
const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
