import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function option(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

const defaultRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const root = path.resolve(option("--project-root", defaultRoot));
const dataPath = path.resolve(option("--data", path.join(root, "build", "uipsd_scan", "workbook_data.json")));
const outputPath = path.resolve(option("--output", path.join(root, "localization", "uipsd_image_text_scan.xlsx")));
const outputDir = path.dirname(outputPath);
const previewDir = path.resolve(option("--preview-dir", path.join(root, "build", "uipsd_scan", "workbook_previews")));
const payload = JSON.parse(await fs.readFile(dataPath, "utf8"));

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const workbook = Workbook.create();
const guideSheet = workbook.worksheets.add("填写说明");
const translationSheet = workbook.worksheets.add("翻译清单");
const detailSheet = workbook.worksheets.add("位置明细");
const rawSheet = workbook.worksheets.add("OCR原始明细");
const imageSheet = workbook.worksheets.add("图片清单");

const colors = {
  navy: "#16324F",
  teal: "#2A9D8F",
  blue: "#3478C4",
  sky: "#DDEBF7",
  pale: "#F4F7FA",
  yellow: "#FFF2B2",
  orange: "#F4A261",
  green: "#D9EAD3",
  red: "#F4CCCC",
  border: "#D0D7DE",
  text: "#1F2937",
  white: "#FFFFFF",
};

function baseSheet(sheet) {
  sheet.showGridLines = false;
  const used = sheet.getRange("A1:Z600");
  used.format.font = { name: "Microsoft YaHei", size: 10, color: colors.text };
  used.format.verticalAlignment = "center";
}

function titleBand(sheet, range, title, subtitle) {
  sheet.getRange(range).merge();
  const topLeft = range.split(":")[0];
  sheet.getRange(topLeft).values = [[title]];
  sheet.getRange(range).format = {
    fill: colors.navy,
    font: { name: "Microsoft YaHei", size: 18, bold: true, color: colors.white },
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 36;
  const startCol = topLeft.replace(/[0-9]/g, "");
  const row = Number(topLeft.replace(/[^0-9]/g, "")) + 1;
  const endCol = range.split(":")[1].replace(/[0-9]/g, "");
  sheet.getRange(`${startCol}${row}:${endCol}${row}`).merge();
  sheet.getRange(`${startCol}${row}`).values = [[subtitle]];
  sheet.getRange(`${startCol}${row}:${endCol}${row}`).format = {
    fill: "#EAF1F8",
    font: { name: "Microsoft YaHei", size: 10, italic: true, color: "#40566D" },
    wrapText: true,
  };
  sheet.getRange(`${startCol}${row}:${endCol}${row}`).format.rowHeight = 28;
}

function styleHeader(range) {
  range.format = {
    fill: colors.blue,
    font: { name: "Microsoft YaHei", size: 10, bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: colors.border },
  };
  range.format.rowHeight = 34;
}

function styleBody(range) {
  range.format = {
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: colors.border },
  };
}

for (const sheet of [guideSheet, translationSheet, detailSheet, rawSheet, imageSheet]) {
  baseSheet(sheet);
}

// Build one editable translation row per globally unique ID.
const uniqueById = new Map();
for (const row of payload.translations) {
  if (!uniqueById.has(row.id)) {
    uniqueById.set(row.id, {
      id: row.id,
      originalText: row.original_text,
      chinese: "",
      language: row.language,
      handling: row.handling,
      files: new Set(),
      colorDescriptions: new Set(),
      fontStyles: new Set(),
      reviewStatuses: new Set(),
      notes: new Set(),
      variantCount: 0,
    });
  }
  const item = uniqueById.get(row.id);
  item.files.add(row.file_name);
  item.colorDescriptions.add(row.color_description);
  item.fontStyles.add(row.font_style);
  item.reviewStatuses.add(row.review_status);
  item.variantCount += Number(row.variant_count || 0);
  if (row.notes) item.notes.add(row.notes);
}
const uniqueRows = [...uniqueById.values()];

// 填写说明
titleBand(
  guideSheet,
  "A1:H1",
  "uipsd 图片文字汉化工作表",
  "已扫描 52 张 PNG；翻译由你填写，坐标、候选色值和字体风格用于后续图片回填。"
);
guideSheet.getRange("A4:B8").values = [
  ["图片总数", "含文字图片"],
  [null, null],
  ["唯一原文条目", "待翻译未填写"],
  [null, null],
  ["OCR 原始框", "已修改中文图集"],
];
guideSheet.getRange("A5:B9").values = [
  [payload.summary.image_count, payload.summary.candidate_image_count],
  [null, null],
  [uniqueRows.length, uniqueRows.filter((row) => row.handling === "待翻译").length],
  [null, null],
  [payload.raw_ocr.length, payload.images.filter((row) => row.scan_status === "已有中文").length],
];
for (const cell of ["A4", "B4", "A6", "B6", "A8", "B8"]) {
  guideSheet.getRange(cell).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
  };
}
for (const cell of ["A5", "B5", "A7", "B7", "A9", "B9"]) {
  guideSheet.getRange(cell).format = {
    fill: colors.pale,
    font: { size: 16, bold: true, color: colors.navy },
    horizontalAlignment: "center",
    borders: { preset: "all", style: "thin", color: colors.border },
  };
}
guideSheet.getRange("D4:H4").merge();
guideSheet.getRange("D4").values = [["填写顺序"]];
guideSheet.getRange("D4:H4").format = {
  fill: colors.teal,
  font: { bold: true, color: colors.white },
  horizontalAlignment: "center",
};
guideSheet.getRange("D5:H10").merge();
guideSheet.getRange("D5").values = [[
  "1. 打开“翻译清单”，只填写黄色的“中文译文”列。\n2. 相同 ID 会在“位置明细”中自动引用同一译文。\n3. 优先处理“处理建议=待翻译”的日文；英文、品牌字和版权可按需保留。\n4. 字色说明为人工视觉分类；候选十六进制色来自识别框像素，最终重绘前请对照原 PNG。\n5. “OCR原始明细”保留全部机器识别框，只用于查漏，不建议直接翻译。"
]];
guideSheet.getRange("D5:H10").format = {
  fill: "#F8FBFD",
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "all", style: "thin", color: colors.border },
};
guideSheet.getRange("A12:H12").merge();
guideSheet.getRange("A12").values = [["状态说明"]];
guideSheet.getRange("A12:H12").format = {
  fill: colors.navy,
  font: { bold: true, color: colors.white },
};
guideSheet.getRange("A13:H17").values = [
  ["待翻译", "日文 UI 文案，建议优先填写", "按需翻译", "英语、数字或品牌内容，由你决定", "建议保留", "版权等固定文本", "人工补录", "OCR 未能可靠定位，原文已人工整理"],
  ["黄色列", "唯一需要手工填写的译文列", "黑／蓝", "常见普通与悬停状态", "白字描边", "常见按钮和标题状态", "候选色值", "识别框内的高频色，不等于最终精确色"],
  ["位置明细", "按图片列出原文、坐标和样式", "OCR原始明细", "443 个机器识别框，用于查漏", "图片清单", "52 张 PNG 的扫描状态", "状态变体数", "同一文本在图集中出现的状态/图块估计数"],
  ["已有中文", "backlog__pack、system0__pack、title__pack", "未见需翻译文字", "背景、图标或纯装饰图", "含文字／已整理", "已进入翻译清单", "坐标需复核", "相邻图块曾被 OCR 合并"],
  ["重要", "翻译后不要改 ID 或文件名", "建议", "中文长度尽量接近日文宽度", "美术", "标题字和粗描边需单独重绘", "透明图集", "导出时保持原尺寸和透明通道"],
];
styleBody(guideSheet.getRange("A13:H17"));
guideSheet.getRange("A13:H17").format.rowHeight = 42;
guideSheet.getRange("A1:H17").format.borders = { preset: "all", style: "thin", color: colors.border };
guideSheet.getRange("A1:H1").format.rowHeight = 34;
guideSheet.getRange("A2:H2").format.rowHeight = 32;
for (const col of ["A", "C", "E", "G"]) guideSheet.getRange(`${col}:${col}`).format.columnWidth = 16;
for (const col of ["B", "D", "F", "H"]) guideSheet.getRange(`${col}:${col}`).format.columnWidth = 29;
guideSheet.freezePanes.freezeRows(2);

// 翻译清单
titleBand(
  translationSheet,
  "A1:L1",
  "翻译清单（只填写黄色列）",
  "每个 ID 只翻译一次；跨图片重复文本共用同一条中文译文。"
);
const translationHeaders = [
  "ID",
  "原文",
  "中文译文",
  "语言",
  "处理建议",
  "来源图片数",
  "状态/图块数",
  "来源文件",
  "字体颜色",
  "字体/描边",
  "复核状态",
  "备注",
];
translationSheet.getRange("A5:L5").values = [translationHeaders];
styleHeader(translationSheet.getRange("A5:L5"));
const translationValues = uniqueRows.map((row) => [
  row.id,
  row.originalText,
  row.chinese,
  row.language,
  row.handling,
  row.files.size,
  row.variantCount,
  [...row.files].join("\n"),
  [...row.colorDescriptions].join("；"),
  [...row.fontStyles].join("；"),
  [...row.reviewStatuses].join("；"),
  [...row.notes].join("；"),
]);
const translationEnd = 5 + translationValues.length;
translationSheet.getRange(`A6:L${translationEnd}`).values = translationValues;
styleBody(translationSheet.getRange(`A6:L${translationEnd}`));
translationSheet.getRange(`C6:C${translationEnd}`).format.fill = colors.yellow;
translationSheet.getRange(`C6:C${translationEnd}`).format.font = { bold: true, color: colors.navy };
translationSheet.getRange(`F6:G${translationEnd}`).format.numberFormat = "0";
translationSheet.getRange(`E6:E${translationEnd}`).dataValidation = {
  rule: { type: "list", values: ["待翻译", "按需翻译", "建议保留", "无需翻译"] },
};
translationSheet.getRange(`K6:K${translationEnd}`).dataValidation = {
  rule: { type: "list", values: ["已人工校正", "已人工校正／坐标需复核", "人工补录／坐标需复核", "已复核"] },
};
translationSheet.getRange(`E6:E${translationEnd}`).conditionalFormats.add("containsText", {
  text: "待翻译",
  format: { fill: "#FCE8D5", font: { color: "#9A3412", bold: true } },
});
translationSheet.getRange(`E6:E${translationEnd}`).conditionalFormats.add("containsText", {
  text: "建议保留",
  format: { fill: colors.green, font: { color: "#256029" } },
});
translationSheet.getRange(`K6:K${translationEnd}`).conditionalFormats.add("containsText", {
  text: "需复核",
  format: { fill: colors.red, font: { color: "#9C0006" } },
});
const translationTable = translationSheet.tables.add(`A5:L${translationEnd}`, true, "UipsdTranslationTable");
translationTable.style = "TableStyleMedium2";
translationTable.showFilterButton = true;
translationSheet.freezePanes.freezeRows(5);
translationSheet.freezePanes.freezeColumns(3);
const translationWidths = [12, 40, 40, 12, 14, 12, 13, 34, 26, 36, 26, 28];
translationWidths.forEach((width, index) => {
  translationSheet.getRangeByIndexes(0, index, translationEnd, 1).format.columnWidth = width;
});
uniqueRows.forEach((row, index) => {
  const sourceLines = row.files.size;
  const textLines = Math.ceil(row.originalText.length / 28);
  const height = Math.min(96, Math.max(38, Math.max(sourceLines, textLines) * 16));
  translationSheet.getRange(`A${index + 6}:L${index + 6}`).format.rowHeight = height;
});

// 位置明细
titleBand(
  detailSheet,
  "A1:Q1",
  "位置明细",
  "按来源图片保留坐标、候选色值和状态数量；中文译文自动引用“翻译清单”。"
);
const detailHeaders = [
  "ID", "文件名", "原文", "中文译文（自动）", "变体数", "X", "Y", "宽", "高", "估计字号(px)",
  "文字色说明", "候选色值", "字体/描边", "OCR置信度", "匹配分数", "复核状态", "备注",
];
detailSheet.getRange("A5:Q5").values = [detailHeaders];
styleHeader(detailSheet.getRange("A5:Q5"));
const detailValues = payload.translations.map((row) => [
  row.id, row.file_name, row.original_text, null, row.variant_count,
  row.x, row.y, row.width, row.height, row.font_size_estimate_px,
  row.color_description, row.palette, row.font_style, row.ocr_confidence,
  row.match_score, row.review_status, row.notes,
]);
const detailEnd = 5 + detailValues.length;
detailSheet.getRange(`A6:Q${detailEnd}`).values = detailValues;
styleBody(detailSheet.getRange(`A6:Q${detailEnd}`));
const translationRowById = new Map(uniqueRows.map((row, index) => [row.id, index + 6]));
detailSheet.getRange(`D6:D${detailEnd}`).formulas = payload.translations.map((row) => [
  `='翻译清单'!$C$${translationRowById.get(row.id)}`,
]);
detailSheet.getRange(`D6:D${detailEnd}`).format.fill = "#FFF9DB";
detailSheet.getRange(`E6:J${detailEnd}`).format.numberFormat = "0";
detailSheet.getRange(`N6:O${detailEnd}`).format.numberFormat = "0.0%";
detailSheet.getRange(`P6:P${detailEnd}`).conditionalFormats.add("containsText", {
  text: "需复核",
  format: { fill: colors.red, font: { color: "#9C0006" } },
});
const detailTable = detailSheet.tables.add(`A5:Q${detailEnd}`, true, "UipsdPositionTable");
detailTable.style = "TableStyleMedium2";
detailSheet.freezePanes.freezeRows(5);
detailSheet.freezePanes.freezeColumns(4);
const detailWidths = [12, 27, 38, 38, 9, 8, 8, 8, 8, 12, 25, 28, 36, 12, 11, 27, 26];
detailWidths.forEach((width, index) => {
  detailSheet.getRangeByIndexes(0, index, detailEnd, 1).format.columnWidth = width;
});
detailSheet.getRange(`A6:Q${detailEnd}`).format.rowHeight = 42;

// OCR 原始明细
titleBand(
  rawSheet,
  "A1:M1",
  "OCR 原始明细（查漏用）",
  "机器识别未经人工逐条纠错；相邻图块可能被拼接，不要直接把本页当作翻译原文。"
);
const rawHeaders = ["OCR ID", "文件名", "机器识别文本", "置信度", "X", "Y", "宽", "高", "方向", "估计字号(px)", "候选色值", "识别底色", "状态"];
rawSheet.getRange("A5:M5").values = [rawHeaders];
styleHeader(rawSheet.getRange("A5:M5"));
const rawValues = payload.raw_ocr.map((row) => [
  row.raw_id, row.file_name, row.text, row.confidence, row.x, row.y,
  row.width, row.height, row.orientation === "vertical" ? "竖排/旋转" : "横排",
  row.font_size_estimate_px, row.palette, row.source_view === "dark" ? "暗底" : "亮底", row.review_status,
]);
const rawEnd = 5 + rawValues.length;
rawSheet.getRange(`A6:M${rawEnd}`).values = rawValues;
styleBody(rawSheet.getRange(`A6:M${rawEnd}`));
rawSheet.getRange(`D6:D${rawEnd}`).format.numberFormat = "0.0%";
rawSheet.getRange(`E6:J${rawEnd}`).format.numberFormat = "0";
rawSheet.getRange(`M6:M${rawEnd}`).conditionalFormats.add("containsText", {
  text: "需复核",
  format: { fill: colors.red, font: { color: "#9C0006" } },
});
const rawTable = rawSheet.tables.add(`A5:M${rawEnd}`, true, "UipsdRawOcrTable");
rawTable.style = "TableStyleMedium2";
rawSheet.freezePanes.freezeRows(5);
rawSheet.freezePanes.freezeColumns(3);
const rawWidths = [12, 28, 52, 12, 8, 8, 8, 8, 12, 12, 30, 10, 14];
rawWidths.forEach((width, index) => rawSheet.getRangeByIndexes(0, index, rawEnd, 1).format.columnWidth = width);
rawSheet.getRange(`A6:M${rawEnd}`).format.rowHeight = 36;

// 图片清单
titleBand(
  imageSheet,
  "A1:J1",
  "uipsd PNG 图片清单",
  "52 张图片的尺寸、扫描状态、文本条目数和来源路径。"
);
const imageHeaders = ["文件名", "类别", "尺寸", "透明通道", "扫描状态", "整理条目数", "OCR框数", "备注", "相对路径", "SHA-256"];
imageSheet.getRange("A5:J5").values = [imageHeaders];
styleHeader(imageSheet.getRange("A5:J5"));
const imageValues = payload.images.map((row) => [
  row.file_name,
  row.category === "pack" ? "图集" : "背景",
  `${row.width} × ${row.height}`,
  row.has_transparency ? "有" : "无",
  row.scan_status,
  row.curated_text_count,
  row.raw_ocr_count,
  row.notes,
  `extracted/_tlg_png/uipsd/${row.file_name}`,
  row.sha256,
]);
const imageEnd = 5 + imageValues.length;
imageSheet.getRange(`A6:J${imageEnd}`).values = imageValues;
styleBody(imageSheet.getRange(`A6:J${imageEnd}`));
imageSheet.getRange(`F6:G${imageEnd}`).format.numberFormat = "0";
imageSheet.getRange(`E6:E${imageEnd}`).conditionalFormats.add("containsText", {
  text: "含文字",
  format: { fill: "#FCE8D5", font: { color: "#9A3412", bold: true } },
});
imageSheet.getRange(`E6:E${imageEnd}`).conditionalFormats.add("containsText", {
  text: "已有中文",
  format: { fill: colors.green, font: { color: "#256029", bold: true } },
});
const imageTable = imageSheet.tables.add(`A5:J${imageEnd}`, true, "UipsdImageTable");
imageTable.style = "TableStyleMedium2";
imageSheet.freezePanes.freezeRows(5);
imageSheet.freezePanes.freezeColumns(1);
const imageWidths = [32, 10, 16, 12, 20, 12, 10, 38, 48, 68];
imageWidths.forEach((width, index) => imageSheet.getRangeByIndexes(0, index, imageEnd, 1).format.columnWidth = width);
imageSheet.getRange(`A6:J${imageEnd}`).format.rowHeight = 32;

// Compact verification and one visual render per sheet.
const translationCheck = await workbook.inspect({
  kind: "table",
  range: "翻译清单!A1:L16",
  include: "values,formulas",
  tableMaxRows: 16,
  tableMaxCols: 12,
  maxChars: 8000,
});
console.log(translationCheck.ndjson);
const detailCheck = await workbook.inspect({
  kind: "table",
  range: "位置明细!A1:Q12",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 17,
  maxChars: 8000,
});
console.log(detailCheck.ndjson);
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 5000,
});
console.log(formulaErrors.ndjson);

const previewRanges = {
  "填写说明": "A1:H17",
  "翻译清单": "A1:L28",
  "位置明细": "A1:Q24",
  "OCR原始明细": "A1:M24",
  "图片清单": "A1:J26",
};
for (const [sheetName, range] of Object.entries(previewRanges)) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, format: "png" });
  const safeName = sheetName.replace(/[^\p{L}\p{N}_-]/gu, "_");
  await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
console.log(`PREVIEW_DIR=${previewDir}`);
console.log(`TRANSLATION_ROWS=${uniqueRows.length}`);
console.log(`DETAIL_ROWS=${payload.translations.length}`);
console.log(`RAW_ROWS=${payload.raw_ocr.length}`);
