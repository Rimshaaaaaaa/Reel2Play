// Build one self-contained script per game template, plus the shared stylesheet and the
// HTML shell. The Python builder (api/src/reel2play/builder) fills the shell with a config.
import { createHash } from "node:crypto";
import { mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { build, transform } from "esbuild";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const templatesDir = path.resolve(root, "../templates");
const dist = path.join(root, "dist");

const sha = (text) => createHash("sha256").update(text).digest("hex").slice(0, 16);

async function templateIds() {
  const entries = await readdir(templatesDir, { withFileTypes: true });
  const ids = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const game = path.join(templatesDir, entry.name, "game.ts");
    if (await stat(game).catch(() => null)) ids.push(entry.name);
  }
  return ids.sort();
}

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

const manifest = { templates: {} };
for (const id of await templateIds()) {
  const result = await build({
    entryPoints: [path.join(templatesDir, id, "game.ts")],
    bundle: true,
    minify: true,
    format: "iife",
    target: "es2020",
    write: false,
    legalComments: "none",
  });
  const code = result.outputFiles[0].text;
  await writeFile(path.join(dist, `${id}.js`), code);
  manifest.templates[id] = { bytes: Buffer.byteLength(code), sha: sha(code) };
}

const css = await transform(await readFile(path.join(root, "src/game.css"), "utf8"), {
  loader: "css",
  minify: true,
  target: ["safari15", "chrome105"],
});
await writeFile(path.join(dist, "game.css"), css.code);
await writeFile(path.join(dist, "shell.html"), await readFile(path.join(root, "src/shell.html")));
manifest.css = { bytes: Buffer.byteLength(css.code), sha: sha(css.code) };
await writeFile(path.join(dist, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify(manifest));
