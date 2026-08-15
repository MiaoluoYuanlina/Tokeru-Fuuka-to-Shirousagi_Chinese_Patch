import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const workspace = path.resolve(import.meta.dirname, "../..");
const sourcePath = path.join(workspace, "localization", "scenario_dialogue_zh_cn.tsv");
const outputDir = path.join(workspace, "outputs", "019ffe40-472a-7932-802b-34ce8d556cae");
const outputPath = path.join(outputDir, "scenario_dialogue_zh_cn.xlsx");
const previewPath = path.join(outputDir, "scenario_dialogue_zh_cn_preview.png");

function parseTsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
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
      row.push(field.endsWith("\r") ? field.slice(0, -1) : field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  if (rows[0]?.[0]?.charCodeAt(0) === 0xfeff) {
    rows[0][0] = rows[0][0].slice(1);
  }
  return rows;
}

const tsv = await fs.readFile(sourcePath, "utf8");
const rows = parseTsv(tsv);
if (rows.length !== 3299 || rows[0].length !== 12) {
  throw new Error(`Unexpected TSV dimensions: ${rows.length} x ${rows[0]?.length}`);
}
for (const row of rows) {
  if (row.length !== 12) throw new Error(`Malformed TSV row with ${row.length} columns`);
}

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("剧情翻译");
sheet.showGridLines = false;
sheet.getRange(`A1:L${rows.length}`).values = rows;
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(5);

const header = sheet.getRange("A1:L1");
header.format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 11 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { bottom: { style: "medium", color: "#17365D" } },
};
header.format.rowHeight = 30;

const data = sheet.getRange(`A2:L${rows.length}`);
data.format = {
  font: { name: "Microsoft YaHei", size: 10 },
  verticalAlignment: "top",
};
data.format.rowHeight = 38;
sheet.getRange(`B2:E${rows.length}`).format = {
  horizontalAlignment: "center",
  verticalAlignment: "top",
  numberFormat: "0",
};
sheet.getRange(`F2:L${rows.length}`).format.wrapText = true;

sheet.getRange(`F2:F${rows.length}`).format.fill = "#EAF2F8";
sheet.getRange(`J2:J${rows.length}`).format.fill = "#EAF2F8";
sheet.getRange(`G2:G${rows.length}`).format.fill = "#FFF2CC";
sheet.getRange(`K2:L${rows.length}`).format.fill = "#FFF2CC";

const widths = {
  A: 18, B: 10, C: 14, D: 11, E: 12, F: 16,
  G: 16, H: 15, I: 14, J: 52, K: 52, L: 28,
};
for (const [column, width] of Object.entries(widths)) {
  sheet.getRange(`${column}:${column}`).format.columnWidth = width;
}

const table = sheet.tables.add(`A1:L${rows.length}`, true, "ScenarioDialogueTable");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "剧情翻译",
  range: "A1:L18",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const inspection = await workbook.inspect({
  kind: "table",
  range: "剧情翻译!A1:L8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 12,
  maxChars: 8000,
});
console.log(inspection.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
const savedWorkbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const savedCheck = await savedWorkbook.inspect({
  kind: "region",
  sheetId: "剧情翻译",
  range: "A1:L3299",
  maxChars: 1000,
});
console.log(savedCheck.ndjson);
console.log(JSON.stringify({ outputPath, previewPath, rows: rows.length, columns: rows[0].length }));
