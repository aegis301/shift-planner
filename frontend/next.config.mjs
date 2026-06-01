/** @type {import('next').NextConfig} */
const apiProxy = process.env.API_PROXY_URL?.trim().replace(/\/$/, "") ?? "";
const allowedDevOrigins = (process.env.ALLOWED_DEV_ORIGINS ?? "localhost,planner.christianporschen.org")
  .split(",")
  .map((entry) => entry.trim())
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins,
  async rewrites() {
    if (!apiProxy) {
      return [];
    }
    return [{ source: "/api/:path*", destination: `${apiProxy}/api/:path*` }];
  },
};

export default nextConfig;
