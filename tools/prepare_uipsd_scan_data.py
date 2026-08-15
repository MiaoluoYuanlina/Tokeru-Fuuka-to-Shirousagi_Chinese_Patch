from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "build" / "uipsd_scan"


CURATED_TEXTS: dict[str, list[str]] = {
    "dialog__pack.png": [
        "この機能が不要な場合は「OFF」を選択してください。",
        "システム設定画面でいつでも再設定が可能です。",
        "データを入れ替えますか？",
        "前回の続きから始めますか？",
        "タイトル画面に戻りますか？",
        "データをコピーしますか？",
        "クイックセーブしますか？",
        "クイックロードしますか？",
        "初期設定に戻しますか？",
        "データを削除しますか？",
        "ゲームを終了しますか？",
        "ジャンプしますか？",
        "上書きしますか？",
        "セーブしますか？",
        "ロードしますか？",
        "次回から表示しない",
        "サスペンド機能",
        "YES",
        "NO",
        "ON",
        "OFF",
    ],
    "file__pack.png": [
        "*DATE",
        "*CHAPTER",
        "*COMMENT",
        "とける風花とシロうさぎ",
        "TOKERU FUUKA TO SHIROUSAGI",
        "No Data",
        "クイックロード",
        "チャプターとコメントを表示",
        "セーブ",
        "ロード",
        "EDITボタンのホールド",
        "データ入れ替え",
        "データコピー",
        "EXTRA BACK",
        "EXTRA LOAD",
        "SAVE",
        "LOAD",
        "NEW!",
        "Q.LOAD",
    ],
    "file_voice__pack.png": [
        "リストに登録",
        "リストを削除",
        "リストから削除",
        "リストをロード",
        "リストをセーブ",
        "プレイリストの表示",
        "EXTRA",
    ],
    "gesture_tips__pack.png": [
        "ドラマチックモード ON/OFF",
        "スクリーンショット保存",
        "バックログ",
        "メッセージスキップ",
        "ボイス再生",
        "前の選択肢へ戻る",
        "お気に入りボイス",
        "シナリオチャート",
        "ウィンドウ消去",
        "ゲームの最小化",
        "タイトルに戻る",
        "クイックセーブ",
    ],
    "popup_quick__bg0.png": [
        "とける風花とシロうさぎ",
        "TOKERU FUUKA TO SHIROUSAGI",
        "No Data",
    ],
    "popup_system__bg0.png": [
        "メッセージ速度",
        "オートプレイ速度",
        "ウィンドウ不透明度",
        "未読スキップ",
    ],
    "popup_system__pack.png": ["既読のみ", "全文"],
    "popup_volume__bg0.png": ["マスター", "BGM", "VOICE", "SE（ゲーム効果音）"],
    "system1__pack.png": [
        "画面サイズ",
        "画面解像度",
        "画面切り替え速度",
        "画面を常に手前に表示",
        "システムメニューポップアップ",
        "サスペンド機能",
        "マウスの設定",
        "スナップショットの保存設定",
        "日時ファイル名で保存",
        "ファイル名を指定",
        "フルスクリーン",
        "ウィンドウ",
        "1024×576",
        "1280×720",
        "1600×900",
        "1920×1080",
        "右クリック",
        "センターホイールクリック",
        "メッセージウィンドウを消去",
        "詳細設定",
        "Type A",
        "Type B",
        "ON",
        "OFF",
        "NoWait",
        "×0.5",
        "×2",
    ],
    "system2__pack.png": [
        "メッセージ速度",
        "既読メッセージの瞬間表示",
        "オートプレイ速度",
        "選択肢後メッセージスキップ",
        "オートプレイ時ボイス完全再生",
        "メッセージスキップ速度",
        "メッセージスキップ設定",
        "Ctrlスキップ設定",
        "メッセージウィンドウ濃度",
        "ドラマチックモード",
        "外部音声ツール連動",
        "サンプルテキスト",
        "既読のみ",
        "全文",
        "中断",
        "継続",
        "ON",
        "OFF",
    ],
    "system3__pack.png": [
        "マスター",
        "BGM",
        "BGM（ボイス再生時）",
        "SE（ゲーム効果音）",
        "SE（システム効果音）",
        "MOVIE",
        "ボイスカット",
        "BGMダウン",
        "キャラクターボイス",
        "システムボイス",
        "その他（女性）",
        "その他（男性）",
        "秋穂",
        "絵利",
        "春香",
        "美世",
        "風花",
        "ALL",
        "ON",
        "OFF",
    ],
    "system4__pack.png": [
        "シーンジャンプ（バックログ）",
        "サスペンド復帰",
        "データ入れ替え",
        "データ削除",
        "クイックセーブ",
        "クイックロード",
        "タイトルに戻る",
        "セーブ（上書き）",
        "ON",
        "OFF",
    ],
    "system5__pack.png": [
        "アドベンチャー画面で右クリックしながらマウスを上下左右に動かすことで、対応した機能が実行されます。",
        "プルダウンメニュー（▼）をクリックしてジェスチャーの項目を変更できます。",
        "右クリック長押しで現在の設定を表示",
        "右クリックジェスチャー",
        "ジェスチャー機能",
        "ドラマチックモード ON/OFF",
        "スクリーンショット保存",
        "メッセージスキップ",
        "お気に入りボイス",
        "ゲームの最小化",
        "バックログ",
        "ボイス再生",
        "システムセーブロード無効",
        "ON",
        "OFF",
    ],
    "system5_pulldown__pack.png": [
        "オートプレイ",
        "バックログ",
        "無効",
        "ウィンドウ消去",
        "ドラマチックモード ON/OFF",
        "お気に入りボイス",
        "ロード",
        "ゲームの最小化",
        "クイックロード",
        "スクリーンショット保存",
        "クイックセーブ",
        "セーブ",
        "メッセージスキップ",
        "スクリーンショット保存",
        "システム",
        "タイトルに戻る",
        "ボイス再生",
    ],
    "system6__pack.png": [
        "プルダウンメニュー（▼）をクリックしてショートカットの項目を変更できます。",
        "メッセージの進行／選択肢の決定",
        "ドラマチックモード ON/OFF",
        "メッセージの強制スキップ",
        "キーボード入力 ON/OFF",
        "ウィンドウサイズの変更",
        "バックログ時に下移動",
        "スクリーンショット保存",
        "マウスの右クリック",
        "メッセージスキップ",
        "固定ショートカット",
        "Space",
        "Ctrl",
        "Page Down",
        "ESC",
        "Enter",
    ],
    "system6_pulldown__pack.png": [
        "ゲーム終了",
        "キーボード入力 ON/OFF",
        "ウィンドウサイズの変更",
        "システム",
    ],
    "title_bg_2.png": ["© 2026 Shiratamaco All Rights Reserved."],
    "title_bg_5.png": ["とける風花とシロうさぎ", "TOKERU FUUKA TO SHIROUSAGI"],
    "title_bg_6.png": ["体験版"],
}


STYLE_BY_FILE = {
    "dialog__pack.png": ("白字／黑字，蓝色强调", "粗黑体；主提示带黑色粗描边"),
    "file__pack.png": ("黑字／白字，蓝色状态字", "粗黑体与窄体混排；部分带黑色描边"),
    "file_voice__pack.png": ("白字／浅蓝字", "按钮用粗黑体；标题带黑色描边"),
    "gesture_tips__pack.png": ("黑字／蓝字／白字", "粗黑体；按钮状态有描边"),
    "popup_quick__bg0.png": ("多色标题、浅灰副标题", "装饰性标题字；品牌图形"),
    "popup_system__bg0.png": ("近黑色", "明朝体／衬线体"),
    "popup_system__pack.png": ("黑字／蓝字", "粗黑体；普通与高亮状态"),
    "popup_volume__bg0.png": ("近黑色", "明朝体／衬线体"),
    "system1__pack.png": ("黑字／蓝字／白字", "粗黑体；普通、悬停、启用、禁用状态"),
    "system2__pack.png": ("黑字／蓝字／白字", "粗黑体；普通、悬停、启用、禁用状态"),
    "system3__pack.png": ("黑字／蓝字／白字", "粗黑体；人物名与开关状态混排"),
    "system4__pack.png": ("黑字／蓝字／白字", "粗黑体；确认弹窗开关状态"),
    "system5__pack.png": ("深蓝字／黑字／白字", "粗黑体；说明文字较小"),
    "system5_pulldown__pack.png": ("白字／浅蓝字", "粗黑体；蓝色菜单普通与悬停状态"),
    "system6__pack.png": ("黑字／蓝字／白字", "粗黑体；含竖排或旋转图块"),
    "system6_pulldown__pack.png": ("白字／浅蓝字", "粗黑体；蓝色菜单普通与悬停状态"),
    "title_bg_2.png": ("白色", "小号版权字；通常保留原文"),
    "title_bg_5.png": ("粉、蓝、灰多色", "手写／装饰标题字；需单独美术重制"),
    "title_bg_6.png": ("白色、淡粉描边", "装饰性粗体；需单独美术重制"),
}


IMAGE_NOTES = {
    "backlog__pack.png": "检测为已修改中文图集；本轮不重复翻译。",
    "system0__pack.png": "检测为已修改中文系统导航图集；本轮不重复翻译。",
    "title__pack.png": "检测为已修改中文标题菜单图集；本轮不重复翻译。",
    "select__bg0.png": "纯背景／透明层，无固定文字。",
    "title_bg_2.png": "仅版权信息，建议保留原文。",
}


def compact(text: str) -> str:
    return re.sub(r"[\s・･／/()（）「」『』.,。!?！？:*＊©×]", "", text).lower()


def similarity(left: str, right: str) -> float:
    a, b = compact(left), compact(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b)) * 0.35 + 0.65
    return SequenceMatcher(None, a, b).ratio()


def language_of(text: str) -> str:
    if re.search(r"[ぁ-ゖァ-ヺ一-龯]", text):
        return "日语"
    if re.search(r"[A-Za-z]", text):
        return "英语／符号"
    return "符号／数字"


def handling_of(text: str) -> str:
    language = language_of(text)
    if text.startswith("©"):
        return "建议保留"
    if language == "日语":
        return "待翻译"
    return "按需翻译"


def confidence_status(score: float, match_score: float) -> str:
    if score >= 0.94 and match_score >= 0.82:
        return "已人工校正"
    if match_score >= 0.55:
        return "已人工校正／坐标需复核"
    return "人工补录／坐标需复核"


def main() -> None:
    manifest = json.loads((BUILD_DIR / "manifest.json").read_text(encoding="utf-8"))
    ocr_payload = json.loads((BUILD_DIR / "ocr_results.json").read_text(encoding="utf-8"))
    ocr_by_file = {item["file_name"]: item["detections"] for item in ocr_payload["results"]}

    translations = []
    translation_id = 1
    seen_global: dict[str, str] = {}
    for file_name, texts in CURATED_TEXTS.items():
        detections = ocr_by_file.get(file_name, [])
        for text in dict.fromkeys(texts):
            ranked = sorted(
                ((similarity(text, d["text"]), d) for d in detections),
                key=lambda pair: (pair[0], pair[1]["confidence"]),
                reverse=True,
            )
            match_score, best = ranked[0] if ranked else (0.0, {})
            related = [
                d
                for d in detections
                if similarity(text, d["text"]) >= 0.82
                or compact(text) in compact(d["text"])
            ]
            identity = compact(text)
            shared_id = seen_global.get(identity)
            current_id = f"UI-{translation_id:04d}"
            if shared_id is None:
                seen_global[identity] = current_id
            else:
                current_id = shared_id
            style_color, style_font = STYLE_BY_FILE.get(
                file_name, ("见候选色值", "按原图复刻")
            )
            translations.append(
                {
                    "id": current_id,
                    "file_name": file_name,
                    "original_text": text,
                    "chinese_translation": "",
                    "language": language_of(text),
                    "handling": handling_of(text),
                    "variant_count": max(1, len(related)),
                    "x": best.get("x"),
                    "y": best.get("y"),
                    "width": best.get("width"),
                    "height": best.get("height"),
                    "font_size_estimate_px": best.get("font_size_estimate_px"),
                    "color_description": style_color,
                    "palette": " / ".join(best.get("palette", [])),
                    "font_style": style_font,
                    "ocr_confidence": best.get("confidence"),
                    "match_score": round(match_score, 3),
                    "review_status": confidence_status(
                        float(best.get("confidence", 0)), match_score
                    ),
                    "notes": "同 ID 表示跨图片重复文本，可共用译文。"
                    if shared_id
                    else "",
                }
            )
            translation_id += 1

    raw_rows = []
    raw_id = 1
    for result in ocr_payload["results"]:
        for detection in result["detections"]:
            raw_rows.append(
                {
                    "raw_id": f"OCR-{raw_id:04d}",
                    "file_name": result["file_name"],
                    **detection,
                    "palette": " / ".join(detection.get("palette", [])),
                    "review_status": "需复核"
                    if detection["confidence"] < 0.9
                    else "原始识别",
                }
            )
            raw_id += 1

    curated_files = set(CURATED_TEXTS)
    image_rows = []
    for item in manifest["files"]:
        file_name = item["file_name"]
        if file_name in {"backlog__pack.png", "system0__pack.png", "title__pack.png"}:
            scan_status = "已有中文"
        elif file_name in curated_files:
            scan_status = "含文字／已整理"
        else:
            scan_status = "未见需翻译文字"
        image_rows.append(
            {
                **item,
                "scan_status": scan_status,
                "curated_text_count": sum(
                    1 for row in translations if row["file_name"] == file_name
                ),
                "raw_ocr_count": len(ocr_by_file.get(file_name, [])),
                "notes": IMAGE_NOTES.get(file_name, ""),
            }
        )

    output = {
        "summary": {
            "image_count": len(image_rows),
            "candidate_image_count": len(curated_files),
            "curated_row_count": len(translations),
            "unique_text_count": len(seen_global),
            "raw_ocr_row_count": len(raw_rows),
        },
        "translations": translations,
        "raw_ocr": raw_rows,
        "images": image_rows,
    }
    output_path = BUILD_DIR / "workbook_data.json"
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(output["summary"], ensure_ascii=False))
    print(f"WORKBOOK_DATA={output_path}")


if __name__ == "__main__":
    main()
