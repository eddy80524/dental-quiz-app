import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraping.targets import targets_by_year, rikougaku_urls, hozon_shufuku_urls, endodontics_urls, shishubyou_urls, kaibougaku_urls, kuraburi_urls, soshikigaku_urls, seirigaku_urls, byouri_urls, yakurigaku_urls, biseibutsu_meneki_urls, eiseigaku_urls, hatsusei_karei_urls, bubunjo_gishi_urls, zenbujo_gishi_urls, implant_urls, kouku_geka_urls, shika_houshasen_urls
from scraping.scrape_dentalyouth import scrape_questions_from

def validate_questions(questions):
    errors = []
    if not isinstance(questions, list):
        errors.append("questionsがlist型ではありません")
        return False, errors
    if len(questions) < 1:
        errors.append(f"問題数が少なすぎます: {len(questions)}問")
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            errors.append(f"{i+1}問目がdict型ではありません")
            continue
        if 'id' not in q and 'number' not in q:
            errors.append(f"{i+1}問目に'id'または'number'がありません")
        if 'text' not in q and 'question' not in q:
            errors.append(f"{i+1}問目に'text'または'question'がありません")
        if 'choices' not in q:
            errors.append(f"{i+1}問目に'choices'がありません")
        if 'answer' not in q:
            errors.append(f"{i+1}問目に'answer'がありません")
    return len(errors) == 0, errors

def scrape_and_save(targets, out_name_func, merge_all=False):
    project_root = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)

    if merge_all:
        # 複数リンクの内容を1つにまとめる
        all_questions = []
        for url in targets:
            print(f"→ fetching from {url}")
            questions = scrape_questions_from(url)
            for q in questions:
                q["source_url"] = url
            all_questions.extend(questions)
        is_valid, errors = validate_questions(all_questions)
        if not is_valid:
            print(f"× invalid data: {out_name_func()} → 保存しません")
            for err in errors:
                print(f"  - {err}")
            return
        out_path = os.path.join(data_dir, out_name_func())
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_questions, f, ensure_ascii=False, indent=2)
        print(f"  saved: {out_path} ({len(all_questions)} questions)")
    else:
        # 回数別（1リンク1ファイル）
        for t in targets:
            year    = t.get("year")
            section = t.get("section")
            url     = t.get("url")
            fname   = out_name_func(year, section)
            out_path = os.path.join(data_dir, fname)
            if os.path.exists(out_path):
                print(f"■ skip: {fname} already exists")
                continue
            print(f"→ fetching from {url}")
            questions = scrape_questions_from(url)
            is_valid, errors = validate_questions(questions)
            if not is_valid:
                print(f"× invalid data: {fname} → 保存しません")
                for err in errors:
                    print(f"  - {err}")
                continue
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
            print(f"  saved: {out_path} ({len(questions)} questions)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["year", "rikougaku", "hozon_shufuku", "endodontics", "shishubyou", "kaibougaku", "kuraburi", "soshikigaku", "seirigaku", "byouri", "yakurigaku", "biseibutsu_meneki", "eiseigaku", "hatsusei_karei", "bubunjo_gishi", "zenbujo_gishi", "implant", "kouku_geka", "shika_houshasen", "shika_masuigaku", "seikagaku"], required=True, help="スクレイピング対象")
    args = parser.parse_args()

    if args.mode == "year":
        scrape_and_save(
            targets_by_year,
            lambda year, section: f"dental_{year}{section}.json",
            merge_all=False
        )
    elif args.mode == "rikougaku":
        scrape_and_save(
            rikougaku_urls,
            lambda: "dental_rikougaku.json",
            merge_all=True
        )
    elif args.mode == "hozon_shufuku":
        scrape_and_save(
            hozon_shufuku_urls,
            lambda: "dental_hozon_shufuku.json",
            merge_all=True
        )
    elif args.mode == "endodontics":
        scrape_and_save(
            endodontics_urls,
            lambda: "dental_endodontics.json",
            merge_all=True
        )
    elif args.mode == "shishubyou":
        scrape_and_save(
            shishubyou_urls,
            lambda: "dental_shishubyou.json",
            merge_all=True
        )
    elif args.mode == "kaibougaku":
        scrape_and_save(
            kaibougaku_urls,
            lambda: "dental_kaibougaku.json",
            merge_all=True
        )
    elif args.mode == "kuraburi":
        scrape_and_save(
            kuraburi_urls,
            lambda: "dental_kuraburi.json",
            merge_all=True
        )
    elif args.mode == "soshikigaku":
        scrape_and_save(
            soshikigaku_urls,
            lambda: "dental_soshikigaku.json",
            merge_all=True
        )
    elif args.mode == "seirigaku":
        scrape_and_save(
            seirigaku_urls,
            lambda: "dental_seirigaku.json",
            merge_all=True
        )
    elif args.mode == "byouri":
        scrape_and_save(
            byouri_urls,
            lambda: "dental_byouri.json",
            merge_all=True
        )
    elif args.mode == "yakurigaku":
        scrape_and_save(
            yakurigaku_urls,
            lambda: "dental_yakurigaku.json",
            merge_all=True
        )
    elif args.mode == "biseibutsu_meneki":
        scrape_and_save(
            biseibutsu_meneki_urls,
            lambda: "dental_biseibutsu_meneki.json",
            merge_all=True
        )
    elif args.mode == "eiseigaku":
        scrape_and_save(
            eiseigaku_urls,
            lambda: "dental_eiseigaku.json",
            merge_all=True
        )
    elif args.mode == "hatsusei_karei":
        scrape_and_save(
            hatsusei_karei_urls,
            lambda: "dental_hatsusei_karei.json",
            merge_all=True
        )
    elif args.mode == "bubunjo_gishi":
        scrape_and_save(
            bubunjo_gishi_urls,
            lambda: "dental_bubunjo_gishi.json",
            merge_all=True
        )
    elif args.mode == "zenbujo_gishi":
        scrape_and_save(
            zenbujo_gishi_urls,
            lambda: "dental_zenbujo_gishi.json",
            merge_all=True
        )
    elif args.mode == "implant":
        scrape_and_save(
            implant_urls,
            lambda: "dental_implant.json",
            merge_all=True
        )
    elif args.mode == "kouku_geka":
        scrape_and_save(
            kouku_geka_urls,
            lambda: "dental_kouku_geka.json",
            merge_all=True
        )
    elif args.mode == "shika_houshasen":
        scrape_and_save(
            shika_houshasen_urls,
            lambda: "dental_shika_houshasen.json",
            merge_all=True
        )
    elif args.mode == "shika_masuigaku":
        from scraping.targets import shika_masuigaku_urls
        scrape_and_save(
            shika_masuigaku_urls,
            lambda: "dental_shika_masuigaku.json",
            merge_all=True
        )
    elif args.mode == "seikagaku":
        from scraping.targets import seikagaku_urls
        scrape_and_save(
            seikagaku_urls,
            lambda: "dental_seikagaku.json",
            merge_all=True
        )