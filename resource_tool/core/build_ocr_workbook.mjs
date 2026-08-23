import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`Missing ${name}`);
  return path.resolve(process.argv[index + 1]);
}

const dataPath = option("--data");
const outputPath = option("--output");
const payload = JSON.parse(await fs.readFile(dataPath, "utf8"));
const headers = ["ID", "相对路径", "源图片绝对路径", "原文", "中文译文", "置信度", "X", "Y", "宽度", "高度", "文字方向", "识别旋转角度", "顺时针阅读角度", "字体颜色", "估计字号", "处理状态", "备注"];
const rows = [];
let id = 1;
for (const file of payload.results ?? []) {
  for (const item of file.detections ?? []) {
    rows.push([
      `OCR-${String(id).padStart(6, "0")}`,
      file.relative_path ?? file.file_name,
      file.source_path ?? path.join(payload.source_directory, file.file_name),
      item.text ?? "",
      "",
      Number(item.confidence ?? 0),
      Number(item.x ?? 0), Number(item.y ?? 0), Number(item.width ?? 0), Number(item.height ?? 0),
      item.orientation ?? "horizontal",
      Number(item.rotation_degrees ?? 0),
      Number(item.read_rotation_clockwise_degrees ?? 0),
      (item.palette ?? ["#202020"])[0] ?? "#202020",
      Number(item.font_size_estimate_px ?? 18),
      "待翻译",
      "",
    ]);
    id += 1;
  }
}

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("OCR翻译");
sheet.showGridLines = false;
sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).values = [headers, ...rows];
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(5);
sheet.getRange(`A1:Q1`).format = {
  fill: "#245B8A", font: { bold: true, color: "#FFFFFF", size: 10 },
  horizontalAlignment: "center", verticalAlignment: "center", wrapText: true,
  borders: { bottom: { style: "medium", color: "#183C5B" } },
};
sheet.getRange("A1:Q1").format.rowHeight = 32;
if (rows.length) {
  const data = sheet.getRange(`A2:Q${rows.length + 1}`);
  data.format.font = { name: "Microsoft YaHei UI", size: 9 };
  data.format.verticalAlignment = "center";
  data.format.rowHeight = 34;
  data.format.borders = { insideHorizontal: { style: "thin", color: "#DCE6EF" } };
  sheet.getRange(`C2:E${rows.length + 1}`).format.wrapText = true;
  sheet.getRange(`Q2:Q${rows.length + 1}`).format.wrapText = true;
  sheet.getRange(`F2:F${rows.length + 1}`).format.numberFormat = "0.0000";
  sheet.getRange(`E2:E${rows.length + 1}`).format.fill = "#FFF3CD";
  sheet.getRange(`P2:P${rows.length + 1}`).dataValidation = { rule: { type: "list", values: ["待翻译", "已翻译", "跳过", "需复核"] } };
  sheet.tables.add(`A1:Q${rows.length + 1}`, true, "OcrTranslationTable").style = "TableStyleMedium2";
}
const widths = [15, 28, 48, 34, 34, 11, 8, 8, 8, 8, 15, 14, 14, 13, 10, 12, 24];
for (let col = 0; col < widths.length; col += 1) sheet.getRangeByIndexes(0, col, Math.max(2, rows.length + 1), 1).format.columnWidth = widths[col];

const info = workbook.worksheets.add("使用说明");
info.showGridLines = false;
info.getRange("A1:F1").merge();
info.getRange("A1").values = [["OCR 图片翻译表使用说明"]];
info.getRange("A1:F1").format = { fill: "#245B8A", font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 34 };
info.getRange("A3:A8").values = [["1"], ["2"], ["3"], ["4"], ["5"], ["6"]];
info.getRange("B3:F8").merge(true);
info.getRange("B3:B8").values = [["只填写“中文译文”列；不修改 ID、路径和坐标。"], ["若不需要替换某条文字，将处理状态改为“跳过”。"], ["字体颜色可填写 #RRGGBB；程序默认使用 OCR 估计颜色。"], ["字号可手动调整；程序会在目标框内自动缩小避免越界。"], ["竖排文字会依据识别旋转角度自动旋转后写回。"], ["处理图片时会保留目录结构，并生成 render_report.json。"]];
info.getRange("B3:F8").format = { wrapText: true, verticalAlignment: "center" };
info.getRange("A3:A8").format = { fill: "#D9EAF7", font: { bold: true }, horizontalAlignment: "center" };
info.getRange("A3:F8").format.rowHeight = 34;
info.getRange("A1:F8").format.columnWidth = 20;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const preview = await workbook.render({ sheetName: "OCR翻译", range: `A1:Q${Math.min(rows.length + 1, 26)}`, scale: 1, format: "png" });
await fs.writeFile(outputPath.replace(/\.xlsx$/i, "_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`ROWS=${rows.length}`);
console.log(`OUTPUT=${outputPath}`);
