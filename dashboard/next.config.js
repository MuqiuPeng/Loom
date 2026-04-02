/** @type {import('next').NextConfig} */
const API_URL = process.env.LOOM_API_URL || "http://localhost:8001";

const nextConfig = {
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/api/profile/:path*", destination: `${API_URL}/api/profile/:path*` },
        { source: "/api/resumes/:path*", destination: `${API_URL}/api/resumes/:path*` },
        { source: "/api/jobs/:path*", destination: `${API_URL}/api/jobs/:path*` },
        { source: "/api/workflow/:path*", destination: `${API_URL}/api/workflow/:path*` },
        { source: "/api/workflows/:path*", destination: `${API_URL}/api/workflows/:path*` },
        { source: "/api/tasks/:path*", destination: `${API_URL}/api/tasks/:path*` },
        { source: "/api/logs/:path*", destination: `${API_URL}/api/logs/:path*` },
        { source: "/api/logs", destination: `${API_URL}/api/logs` },
        { source: "/api/health", destination: `${API_URL}/api/health` },
      ],
    };
  },
};

module.exports = nextConfig;
