/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import reactPlugin from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig({
  plugins: [
    // disable React Fast Refresh to prevent Vite HMR websocket injection
    // @ts-expect-error fastRefresh is not in types
    reactPlugin({ fastRefresh: false }),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["coachiq-icon-192.png", "coachiq-icon-512.png"],
      manifest: {
        name: "CoachIQ",
        short_name: "CoachIQ",
        description: "Offline-aware RV coach monitoring and control",
        theme_color: "#111827",
        background_color: "#111827",
        display: "standalone",
        orientation: "any",
        start_url: "/",
        scope: "/",
        icons: [
          {
            src: "/coachiq-icon-192.png",
            sizes: "192x192",
            type: "image/png"
          },
          {
            src: "/coachiq-icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable"
          }
        ]
      },
      workbox: {
        clientsClaim: true,
        skipWaiting: true,
        navigateFallback: "/index.html",
        globPatterns: ["**/*.{js,css,html,png,svg,woff2}"],
        runtimeCaching: [
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/"),
            handler: "NetworkOnly",
            method: "GET"
          },
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/"),
            handler: "NetworkOnly",
            method: "POST"
          },
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/"),
            handler: "NetworkOnly",
            method: "PUT"
          },
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/"),
            handler: "NetworkOnly",
            method: "PATCH"
          },
          {
            urlPattern: ({ url }) =>
              url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/"),
            handler: "NetworkOnly",
            method: "DELETE"
          }
        ]
      },
      devOptions: {
        enabled: false
      }
    }),
    // Bundle analyzer for performance optimization
    ...(process.env.ANALYZE === "true"
      ? [
          visualizer({
            filename: "dist/stats.html",
            open: false,
            gzipSize: true,
            brotliSize: true
          })
        ]
      : [])
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      // Ensure single React copy and runtime to avoid invalid hook calls
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
      "react/jsx-runtime": path.resolve(__dirname, "node_modules/react/jsx-runtime.js"),
      "react/jsx-dev-runtime": path.resolve(__dirname, "node_modules/react/jsx-dev-runtime.js"),
      // Add alias for tabler icons to improve tree-shaking and prevent full library processing
      "@tabler/icons-react$": path.resolve(__dirname, "node_modules/@tabler/icons-react/dist/esm/index.js"),
    },
    // Prevent duplicate React copies
    dedupe: ['react', 'react-dom'],
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: true,
  },
  // Development server optimizations to prevent resource exhaustion
  server: {
    // completely disable Vite HMR
    hmr: false,
    // Limit the number of concurrent requests to prevent browser resource exhaustion
    middlewareMode: false,
    // No custom Cache-Control here: source modules (/src/*) are unhashed, so a
    // long max-age makes browsers serve stale code across dev-server restarts.
    // Vite's defaults already cache correctly (etag for sources, immutable for
    // hashed /node_modules/.vite/deps); production headers come from the proxy.
    // Proxy API requests to the backend server (WebSockets connect directly)
    proxy: {
      // Proxy REST API requests
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        rewrite: (path) => path,
      },
      // Proxy WebSocket requests to backend
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  optimizeDeps: {
    // Pre-bundle specific Tabler icons to prevent resource exhaustion
    include: [
      'react',
      'react-dom',
      'react-router-dom',
      // Only include the specific icons we actually use
      '@tabler/icons-react/dist/esm/icons/IconCamera.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChartBar.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChevronDown.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChevronLeft.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChevronRight.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChevronsLeft.mjs',
      '@tabler/icons-react/dist/esm/icons/IconChevronsRight.mjs',
      '@tabler/icons-react/dist/esm/icons/IconCircleCheckFilled.mjs',
      '@tabler/icons-react/dist/esm/icons/IconCirclePlusFilled.mjs',
      '@tabler/icons-react/dist/esm/icons/IconCreditCard.mjs',
      '@tabler/icons-react/dist/esm/icons/IconDashboard.mjs',
      '@tabler/icons-react/dist/esm/icons/IconDatabase.mjs',
      '@tabler/icons-react/dist/esm/icons/IconDeviceDesktop.mjs',
      '@tabler/icons-react/dist/esm/icons/IconDots.mjs',
      '@tabler/icons-react/dist/esm/icons/IconDotsVertical.mjs',
      '@tabler/icons-react/dist/esm/icons/IconFileAi.mjs',
      '@tabler/icons-react/dist/esm/icons/IconFileDescription.mjs',
      '@tabler/icons-react/dist/esm/icons/IconFileWord.mjs',
      '@tabler/icons-react/dist/esm/icons/IconFolder.mjs',
      '@tabler/icons-react/dist/esm/icons/IconGripVertical.mjs',
      '@tabler/icons-react/dist/esm/icons/IconHelp.mjs',
      '@tabler/icons-react/dist/esm/icons/IconInnerShadowTop.mjs',
      '@tabler/icons-react/dist/esm/icons/IconLayoutColumns.mjs',
      '@tabler/icons-react/dist/esm/icons/IconListDetails.mjs',
      '@tabler/icons-react/dist/esm/icons/IconLoader.mjs',
      '@tabler/icons-react/dist/esm/icons/IconLogout.mjs',
      '@tabler/icons-react/dist/esm/icons/IconMail.mjs',
      '@tabler/icons-react/dist/esm/icons/IconMoon.mjs',
      '@tabler/icons-react/dist/esm/icons/IconNotification.mjs',
      '@tabler/icons-react/dist/esm/icons/IconPlus.mjs',
      '@tabler/icons-react/dist/esm/icons/IconReport.mjs',
      '@tabler/icons-react/dist/esm/icons/IconSearch.mjs',
      '@tabler/icons-react/dist/esm/icons/IconSettings.mjs',
      '@tabler/icons-react/dist/esm/icons/IconShare3.mjs',
      '@tabler/icons-react/dist/esm/icons/IconSun.mjs',
      '@tabler/icons-react/dist/esm/icons/IconTrash.mjs',
      '@tabler/icons-react/dist/esm/icons/IconTrendingDown.mjs',
      '@tabler/icons-react/dist/esm/icons/IconTrendingUp.mjs',
      '@tabler/icons-react/dist/esm/icons/IconUserCircle.mjs'
    ],
    // Force optimization to only process our specified icons
    force: true,
  },
  build: {
    // Reduce memory usage for ARM systems like Raspberry Pi
    target: 'es2015',
    minify: 'esbuild', // Faster than terser, uses less memory
    rollupOptions: {
      // Cap concurrent file reads: the @tabler/icons-react ESM index pulls in
      // thousands of modules and unbounded parallel opens can exhaust the fd
      // limit (EMFILE) on constrained systems (Raspberry Pi, sandboxes).
      maxParallelFileOps: 64,
      output: {
        manualChunks: {
          router: ['react-router-dom'],
          ui: ['@radix-ui/react-checkbox', '@radix-ui/react-dialog'],
          charts: ['recharts', '@tanstack/react-table'],
          // Remove @tabler/icons-react from manual chunks to allow tree-shaking
          icons: ['lucide-react'],
        },
      },
    },
    // Increase chunk size warning limit or keep it for monitoring
    chunkSizeWarningLimit: 1000,
  },
});
