import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(appRoot, "../..");
const labelsPath = path.join(repoRoot, "data/labels/faf_modsmaps_labels.csv");
const inventoryPath = path.join(repoRoot, "data/manifests/faf_modsmaps_inventory.json");
const outPath = path.join(appRoot, "src/data/maps.json");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];

    if (char === "\"" && inQuotes && next === "\"") {
      cell += "\"";
      index += 1;
    } else if (char === "\"") {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") index += 1;
      row.push(cell);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  const [headers, ...records] = rows;
  return records.map((record) =>
    Object.fromEntries(headers.map((header, index) => [header, record[index] ?? ""])),
  );
}

function toTitle(value) {
  return value
    .replace(/\.v\d+$/i, "")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function numeric(value) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function fafPreviewUrl(mapDir, size = "large") {
  return `https://content.faforever.com/maps/previews/${size}/${encodeURIComponent(
    mapDir.toLowerCase(),
  )}.png`;
}

const labels = parseCsv(await readFile(labelsPath, "utf8"));
let inventoryByDir = new Map();

try {
  const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
  inventoryByDir = new Map(inventory.maps.map((map) => [map.map_dir, map]));
} catch {
  inventoryByDir = new Map();
}

const maps = labels.map((label, index) => {
  const inventoryMap = inventoryByDir.get(label.map_dir);
  const previewUrl = fafPreviewUrl(label.map_dir);
  return {
    id: `map_${index + 1}`,
    mapDir: label.map_dir,
    canonicalName: label.canonical_name || toTitle(label.map_dir),
    version: label.version || label.map_dir.match(/\.v(\d+)$/i)?.[1] || "",
    sizeX: numeric(label.size_x),
    sizeZ: numeric(label.size_z),
    playerCount: numeric(label.player_count),
    inventorySource: "data/labels/faf_modsmaps_labels.csv",
    previewUrl,
    structuralPreviewUrl: null,
    hasPreview:
      label.has_preview === "true" ||
      Boolean(inventoryMap?.preview_images?.length) ||
      Boolean(inventoryMap?.other_images?.length),
  };
});

await mkdir(path.dirname(outPath), { recursive: true });
await writeFile(outPath, `${JSON.stringify(maps, null, 2)}\n`);
console.log(`Wrote ${maps.length} map records to ${path.relative(repoRoot, outPath)}`);
