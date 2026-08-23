import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return path.resolve(process.argv[index + 1]);
}
const workbookPath = option("--workbook");
const outputPath = option("--output");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItem("OCR翻译");
const values = sheet.getUsedRange(true).values;
const headers = values[0].map((x) => String(x ?? "").trim());
for (const required of ["ID", "相对路径", "源图片绝对路径", "原文", "中文译文", "X", "Y", "宽度", "高度"]) {
  if (!headers.includes(required)) throw new Error(`表格缺少必需列：${required}`);
}
const rows = values.slice(1).filter((row) => String(row[0] ?? "").trim()).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, JSON.stringify({ workbook: workbookPath, rows }, null, 2), "utf8");
console.log(`ROWS=${rows.length}`);

