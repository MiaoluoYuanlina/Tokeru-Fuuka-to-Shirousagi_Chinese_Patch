import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workspace = path.resolve(import.meta.dirname, "../..");
const inputPath = path.join(workspace, "localization", "scenario_dialogue_zh_cn.xlsx");
const originalTsvPath = path.join(workspace, "localization", "scenario_dialogue_zh_cn.tsv");
const outputPath = path.join(workspace, "localization", "scenario_dialogue_zh_cn_from_excel.tsv");
const previewPath = "C:/Users/XiaoM/.codex/visualizations/2026/08/14/019ffe40-472a-7932-802b-34ce8d556cae/scenario_excel_input_preview.png";

const expectedHeaders = [
  "source_file",
  "scene_index",
  "scene_label",
  "text_index",
  "segment_index",
  "speaker_original",
  "speaker_zh_cn",
  "voice",
  "display_prefix",
  "original_text",
  "translation_zh_cn",
  "translator_note",
];

function normalizeCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  return String(value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function quoteTsv(value) {
  const text = normalizeCell(value);
  if (/[\t\r\n"]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

function encodeTsv(rows) {
  return "\ufeff" + rows.map((row) => row.map(quoteTsv).join("\t")).join("\r\n") + "\r\n";
}

function parseTsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  let start = 0;
  if (text.charCodeAt(0) === 0xfeff) start = 1;
  for (let i = start; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          quoted = false;
        }
      } else {
        field += ch;
      }
    } else if (ch === '"' && field.length === 0) {
      quoted = true;
    } else if (ch === "\t") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      if (field.endsWith("\r")) field = field.slice(0, -1);
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const workbookSummary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 5000,
  tableMaxRows: 5,
  tableMaxCols: 12,
});
console.log(workbookSummary.ndjson);

const sheet = workbook.worksheets.getItemAt(0);
const usedRange = sheet.getUsedRange(true);
const rawRows = usedRange.values;
const rows = rawRows.map((row) => row.map(normalizeCell));

if (rows.length !== 3299) throw new Error(`Expected 3299 rows, found ${rows.length}`);
if (rows.some((row) => row.length !== 12)) throw new Error("Workbook contains rows that are not 12 columns wide");
if (expectedHeaders.some((header, index) => rows[0][index] !== header)) {
  throw new Error(`Unexpected header row: ${JSON.stringify(rows[0])}`);
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan",
});
console.log(formulaErrors.ndjson);

const sample = await workbook.inspect({
  kind: "table",
  range: `${sheet.name}!A1:L8`,
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 12,
  maxChars: 7000,
});
console.log(sample.ndjson);

const preview = await workbook.render({
  sheetName: sheet.name,
  range: "A1:L18",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

let locatorMismatches = 0;
try {
  const originalRows = parseTsv(await fs.readFile(originalTsvPath, "utf8"));
  if (originalRows.length === rows.length) {
    for (let r = 1; r < rows.length; r += 1) {
      for (const c of [0, 1, 2, 3, 4, 5, 7, 8, 9]) {
        if (rows[r][c] !== originalRows[r][c]) locatorMismatches += 1;
      }
    }
  } else {
    locatorMismatches = -1;
  }
} catch {
  locatorMismatches = -1;
}
if (locatorMismatches !== 0) {
  throw new Error(`Source/locator cells changed compared with the original TSV: ${locatorMismatches}`);
}

const encoded = encodeTsv(rows);
await fs.writeFile(outputPath, encoded, "utf8");
const roundTrip = parseTsv(await fs.readFile(outputPath, "utf8"));
if (roundTrip.length !== rows.length || roundTrip.some((row) => row.length !== 12)) {
  throw new Error("TSV round-trip dimensions do not match the workbook");
}
for (let r = 0; r < rows.length; r += 1) {
  for (let c = 0; c < 12; c += 1) {
    if (roundTrip[r][c] !== rows[r][c]) throw new Error(`TSV round-trip mismatch at row ${r + 1}, column ${c + 1}`);
  }
}

const translatedRows = rows.slice(1).filter((row) => row[10].trim() !== "").length;
const translatedSpeakers = rows.slice(1).filter((row) => row[6].trim() !== "").length;
console.log(JSON.stringify({
  inputPath,
  outputPath,
  rows: rows.length,
  dataRows: rows.length - 1,
  columns: rows[0].length,
  translatedRows,
  translatedSpeakers,
  locatorMismatches,
}));
