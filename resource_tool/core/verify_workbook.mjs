import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const path = process.argv[2];
if (!path) throw new Error("Workbook path is required");
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
const summary = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 5000, tableMaxRows: 8, tableMaxCols: 18 });
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 3000 });
console.log(summary.ndjson);
console.log(errors.ndjson);
