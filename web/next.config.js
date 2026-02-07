/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: '/history',
        destination: '/analytics',
        permanent: true,
      },
      {
        source: '/performance',
        destination: '/analytics',
        permanent: true,
      },
    ];
  },
};

module.exports = nextConfig;
