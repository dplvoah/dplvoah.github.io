import { defineConfig } from "astro/config";
import charmTheme from "./charm.theme.mjs";

export default defineConfig({
  prefetch: true,
  site: "https://dplvoah.github.io",
  integrations: [charmTheme],
});
