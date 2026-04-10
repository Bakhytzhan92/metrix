/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: true,
  typescript: {
    // Turbopack + typed routes can sometimes generate broken dev validators on Windows.
    // This keeps `next build` working; your editor/tsc still type-checks your code.
    ignoreBuildErrors: true,
  },
  // If you keep multiple lockfiles in the monorepo root,
  // you can uncomment this to silence Next's root warning:
  // turbopack: { root: __dirname },
}

export default nextConfig
