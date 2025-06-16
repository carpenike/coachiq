/// <reference types="vitest" />
import tailwindcss from "@tailwindcss/vite";
import reactPlugin from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig({
  plugins: [
    // disable React Fast Refresh to prevent Vite HMR websocket injection
    // @ts-expect-error fastRefresh is not in types
    reactPlugin({ fastRefresh: false }),
    tailwindcss(),
    // Bundle analyzer for performance optimization
    visualizer({
      filename: 'dist/stats.html',
      open: true,
      gzipSize: true,
      brotliSize: true
    }),
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
    css: true,
  },
  // Development server optimizations to prevent resource exhaustion
  server: {
    // completely disable Vite HMR
    hmr: false,
    // Limit the number of concurrent requests to prevent browser resource exhaustion
    middlewareMode: false,
    // Enable caching for better performance
    headers: {
      'Cache-Control': 'max-age=31536000',
    },
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
      output: {
        manualChunks: {
          // Separate vendor libraries for better caching
          vendor: ['react', 'react-dom'],
          router: ['react-router-dom'],
          ui: ['@radix-ui/react-avatar', '@radix-ui/react-checkbox', '@radix-ui/react-dialog'],
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
