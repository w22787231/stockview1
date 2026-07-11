import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const workflow = fs.readFileSync(path.join(here, "..", ".github", "workflows", "export-and-deploy.yml"), "utf8");

test("Cloudflare Pages deployment binds Workers AI as env.AI", () => {
  assert.match(workflow, /pages deploy public[^\n]*--ai\s+AI/);
});
