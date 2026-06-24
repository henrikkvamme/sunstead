import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite-plus";

const isVitest = process.env.VITEST === "true";

const config = defineConfig({
  fmt: {
    ignorePatterns: ["src/routeTree.gen.ts"],
    printWidth: 100,
    sortImports: true,
    sortPackageJson: true,
    sortTailwindcss: true,
  },
  lint: {
    jsPlugins: [{ name: "vite-plus", specifier: "vite-plus/oxlint-plugin" }],
    rules: { "vite-plus/prefer-vite-plus-imports": "error" },
    options: { typeAware: true, typeCheck: true },
  },
  resolve: { tsconfigPaths: true },
  server: {
    allowedHosts: ["vps.goose-viper.ts.net"],
  },
  plugins: [
    tailwindcss(),
    tanstackStart(),
    viteReact(),
    isVitest ? null : nitro({ preset: "bun" }),
  ],
});

export default config;
