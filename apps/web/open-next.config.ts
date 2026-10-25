import { defineCloudflareConfig } from "@opennextjs/cloudflare";

export default defineCloudflareConfig({
  compatibilityFlags: ["nodejs_compat"],
});
