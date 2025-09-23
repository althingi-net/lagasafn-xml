import { defineConfig } from "@solidjs/start/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  ssr: false,
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
