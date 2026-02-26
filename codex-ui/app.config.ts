import { defineConfig } from "@solidjs/start/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  ssr: false,
  server: {
    preset: "static",
    baseURL: process.env.NODE_ENV === 'production' ? '/__CODEX_UI_BASE_PATH__/' : '/',
  },
  vite({ router }) {
    const base = {
      plugins: [tailwindcss()],
    };

    if (router === "client") {
      return {
        ...base,
        server: {
          port: 3000,
          strictPort: true,
          hmr: {
            port: 3500,
            clientPort: 3000,
            host: "localhost",
            protocol: "ws",
          },
        },
      };
    }

    return base;
  },

});
