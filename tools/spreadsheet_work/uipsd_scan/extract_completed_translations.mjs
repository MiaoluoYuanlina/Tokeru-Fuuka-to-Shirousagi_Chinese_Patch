import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const defaultRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const root = path.resolve(option("--project-root", defaultRoot));
const workbookPath = path.resolve(option("--workbook", path.join(root, "localization", "uipsd_image_text_scan.xlsx")));
const outputDir = path.resolve(option("--output-dir", path.join(root, "build", "uipsd_localize")));
await fs.mkdir(outputDir, { recursive: true });

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 8000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 100,
});
console.log(summary.ndjson);

const sheet = workbook.worksheets.getItem("翻译清单");
const used = sheet.getUsedRange(true);
const values = used.values;
const headerIndex = values.findIndex((row) => row?.[0] === "ID" && row?.[1] === "原文");
if (headerIndex < 0) throw new Error("未找到翻译清单表头");
const headers = values[headerIndex].map((value) => String(value ?? "").trim());
const rows = [];
for (const sourceRow of values.slice(headerIndex + 1)) {
  const id = String(sourceRow?.[0] ?? "").trim();
  if (!id) continue;
  const row = Object.fromEntries(headers.map((header, index) => [header, sourceRow[index] ?? null]));
  rows.push({
    id,
    original_text: String(row["原文"] ?? "").trim(),
    chinese_translation: String(row["中文译文"] ?? "").trim(),
    language: String(row["语言"] ?? "").trim(),
    handling: String(row["处理建议"] ?? "").trim(),
    source_files: String(row["来源文件"] ?? "").split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
    color_description: String(row["字体颜色"] ?? "").trim(),
    font_style: String(row["字体/描边"] ?? "").trim(),
    review_status: String(row["复核状态"] ?? "").trim(),
    notes: String(row["备注"] ?? "").trim(),
  });
}

const missingRequired = rows.filter((row) => row.handling === "待翻译" && !row.chinese_translation);
const completed = rows.filter((row) => row.chinese_translation);
const overlong = completed.filter((row) => row.chinese_translation.length > Math.max(10, row.original_text.length * 1.6));
const duplicateIds = [...new Set(rows.map((row) => row.id).filter((id, index, all) => all.indexOf(id) !== index))];

const preview = await workbook.render({ sheetName: "翻译清单", range: "A1:L35", scale: 1.2, format: "png" });
await fs.writeFile(`${outputDir}/translation_sheet_preview.png`, new Uint8Array(await preview.arrayBuffer()));

const payload = {
  workbook_path: workbookPath,
  summary: {
    total_rows: rows.length,
    completed_rows: completed.length,
    missing_required_rows: missingRequired.length,
    overlong_rows: overlong.length,
    duplicate_id_count: duplicateIds.length,
  },
  missing_required: missingRequired,
  overlong,
  duplicate_ids: duplicateIds,
  rows,
};
await fs.writeFile(`${outputDir}/translations_from_excel.json`, JSON.stringify(payload, null, 2), "utf8");
console.log(JSON.stringify(payload.summary));
console.log(`OUTPUT=${outputDir}/translations_from_excel.json`);
console.log(`PREVIEW=${outputDir}/translation_sheet_preview.png`);
if (duplicateIds.length) {
  throw new Error(`翻译表中存在重复 ID：${duplicateIds.join(", ")}`);
}
if (missingRequired.length) {
  throw new Error(`仍有 ${missingRequired.length} 条“待翻译”内容未填写中文译文`);
}
