from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FONT = ROOT / "runtime" / "fonts" / "SourceHanSerifSC-Heavy.otf"


def number(row: dict, name: str, default: float = 0) -> int:
    try: return int(float(row.get(name, default)))
    except (TypeError, ValueError): return int(default)


def color(value: object) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(value).strip())
    if not match: return (32, 32, 32, 255)
    raw = match.group(1); return (int(raw[0:2],16), int(raw[2:4],16), int(raw[4:6],16), 255)


def background(image: Image.Image, box: tuple[int,int,int,int]) -> tuple[int,int,int,int]:
    rgba=image.convert("RGBA"); x1,y1,x2,y2=box; points=[]
    for x in range(max(0,x1-2),min(rgba.width,x2+2)):
        for y in (max(0,y1-2),min(rgba.height-1,y2+1)): points.append(rgba.getpixel((x,y)))
    for y in range(max(0,y1-2),min(rgba.height,y2+2)):
        for x in (max(0,x1-2),min(rgba.width-1,x2+1)): points.append(rgba.getpixel((x,y)))
    return Counter(points).most_common(1)[0][0] if points else (255,255,255,0)


def fit(text: str, size: tuple[int,int], requested: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    width,height=size; current=max(6,requested)
    while current>=6:
        font=ImageFont.truetype(str(DEFAULT_FONT),current); words=list(text); lines=[]; line=""
        for ch in words:
            trial=line+ch
            if ImageDraw.Draw(Image.new("L",(1,1))).textbbox((0,0),trial,font=font)[2] <= width or not line: line=trial
            else: lines.append(line); line=ch
        if line: lines.append(line)
        bbox=ImageDraw.Draw(Image.new("L",(1,1))).multiline_textbbox((0,0),"\n".join(lines),font=font,spacing=max(1,current//8),align="center")
        if bbox[2]-bbox[0]<=width and bbox[3]-bbox[1]<=height: return font,lines
        current-=1
    return ImageFont.truetype(str(DEFAULT_FONT),6),[text]


def render_text(text: str, box_size: tuple[int,int], font_size: int, fill: tuple[int,int,int,int], rotation: int) -> Image.Image:
    width,height=box_size
    logical=(height,width) if rotation in (90,270) else (width,height)
    layer=Image.new("RGBA",logical,(0,0,0,0)); font,lines=fit(text,logical,font_size); draw=ImageDraw.Draw(layer)
    joined="\n".join(lines); bbox=draw.multiline_textbbox((0,0),joined,font=font,spacing=max(1,font.size//8),align="center")
    x=(logical[0]-(bbox[2]-bbox[0]))//2-bbox[0]; y=(logical[1]-(bbox[3]-bbox[1]))//2-bbox[1]
    draw.multiline_text((x,y),joined,font=font,fill=fill,spacing=max(1,font.size//8),align="center")
    if rotation==90: layer=layer.transpose(Image.Transpose.ROTATE_270)
    elif rotation==270: layer=layer.transpose(Image.Transpose.ROTATE_90)
    if layer.size!=(width,height): layer=layer.resize((width,height),Image.Resampling.LANCZOS)
    return layer


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--data",required=True,type=Path); parser.add_argument("--output",required=True,type=Path); args=parser.parse_args()
    payload=json.loads(args.data.read_text(encoding="utf-8")); output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    groups=defaultdict(list)
    for row in payload.get("rows",[]):
        translation=str(row.get("中文译文","")).strip(); status=str(row.get("处理状态","")).strip()
        if translation and status!="跳过": groups[str(row.get("源图片绝对路径","")).strip()].append(row)
    report=[]
    for source_name,rows in groups.items():
        source=Path(source_name); relative=Path(str(rows[0].get("相对路径") or source.name)); destination=output/relative; destination.parent.mkdir(parents=True,exist_ok=True)
        image=Image.open(source).convert("RGBA"); original_size=image.size
        for row in rows:
            x,y,w,h=(number(row,"X"),number(row,"Y"),max(1,number(row,"宽度",1)),max(1,number(row,"高度",1))); box=(x,y,min(image.width,x+w),min(image.height,y+h))
            fill_bg=background(image,box); patch=Image.new("RGBA",(box[2]-box[0],box[3]-box[1]),fill_bg); image.alpha_composite(patch,(box[0],box[1]))
            layer=render_text(str(row["中文译文"]),patch.size,max(6,number(row,"估计字号",18)),color(row.get("字体颜色")),number(row,"识别旋转角度"))
            image.alpha_composite(layer,(box[0],box[1])); report.append({"id":row.get("ID"),"source":str(source),"output":str(destination),"box":list(box),"translation":row["中文译文"]})
        image.save(destination)
        if Image.open(destination).size!=original_size: raise ValueError(f"输出尺寸变化：{destination}")
    (output/"render_report.json").write_text(json.dumps({"images":len(groups),"replacements":len(report),"entries":report},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"IMAGES={len(groups)} REPLACEMENTS={len(report)} OUTPUT={output}")


if __name__=="__main__": main()
