import { defineConfig } from "@solidjs/start/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  vite: {
    plugins: [tailwindcss()],
    server: {
      port: 3000,
      strictPort: true,
      hmr: {
        clientPort: 3000,
        host: "localhost",
        protocol: "ws"
      }
    }
  }
});
