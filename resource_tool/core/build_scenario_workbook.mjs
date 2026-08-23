import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

function option(name) { const i = process.argv.indexOf(name); if (i < 0 || !process.argv[i + 1]) throw new Error(`Missing ${name}`); return path.resolve(process.argv[i + 1]); }
function parseTsv(text) {
  const rows=[]; let row=[], field="", quoted=false;
  for(let i=0;i<text.length;i+=1){const ch=text[i]; if(quoted){if(ch==='"'){if(text[i+1]==='"'){field+='"';i+=1;}else quoted=false;}else field+=ch;}else if(ch==='"'&&field.length===0)quoted=true;else if(ch==='\t'){row.push(field);field="";}else if(ch==='\n'){row.push(field.endsWith('\r')?field.slice(0,-1):field);rows.push(row);row=[];field="";}else field+=ch;}
  if(field.length||row.length){row.push(field);rows.push(row);} if(rows[0]?.[0]?.charCodeAt(0)===0xfeff) rows[0][0]=rows[0][0].slice(1); return rows;
}
const tsvPath=option("--tsv"), outputPath=option("--output");
const rows=parseTsv(await fs.readFile(tsvPath,"utf8"));
if(rows.length<2) throw new Error("剧情 TSV 没有数据");
const workbook=Workbook.create(); const sheet=workbook.worksheets.add("剧情翻译"); sheet.showGridLines=false;
sheet.getRangeByIndexes(0,0,rows.length,rows[0].length).values=rows; sheet.freezePanes.freezeRows(1); sheet.freezePanes.freezeColumns(5);
sheet.getRangeByIndexes(0,0,1,rows[0].length).format={fill:"#1F4E78",font:{bold:true,color:"#FFFFFF",size:10},horizontalAlignment:"center",verticalAlignment:"center",wrapText:true};
sheet.getRangeByIndexes(0,0,1,rows[0].length).format.rowHeight=30;
const translationIndex=rows[0].indexOf("translation_zh_cn"); const speakerIndex=rows[0].indexOf("speaker_zh_cn");
if(translationIndex>=0) sheet.getRangeByIndexes(1,translationIndex,rows.length-1,1).format.fill="#FFF3CD";
if(speakerIndex>=0) sheet.getRangeByIndexes(1,speakerIndex,rows.length-1,1).format.fill="#E2F0D9";
const widths=[22,10,20,10,10,18,18,20,12,34,38,24]; for(let i=0;i<rows[0].length;i+=1) sheet.getRangeByIndexes(0,i,rows.length,1).format.columnWidth=widths[i]??18;
sheet.getRangeByIndexes(1,0,rows.length-1,rows[0].length).format={font:{name:"Microsoft YaHei UI",size:9},verticalAlignment:"center",borders:{insideHorizontal:{style:"thin",color:"#E1E8EF"}}};
sheet.getRangeByIndexes(1,0,rows.length-1,rows[0].length).format.rowHeight=30;
for(const index of [9,10,11]) if(index<rows[0].length) sheet.getRangeByIndexes(1,index,rows.length-1,1).format.wrapText=true;
sheet.tables.add(`A1:L${rows.length}`,true,"ScenarioTranslationTable").style="TableStyleMedium2";
await fs.mkdir(path.dirname(outputPath),{recursive:true}); const preview=await workbook.render({sheetName:"剧情翻译",range:`A1:L${Math.min(rows.length,24)}`,scale:1,format:"png"}); await fs.writeFile(outputPath.replace(/\.xlsx$/i,"_preview.png"),new Uint8Array(await preview.arrayBuffer()));
const output=await SpreadsheetFile.exportXlsx(workbook); await output.save(outputPath); console.log(`ROWS=${rows.length-1}`);
