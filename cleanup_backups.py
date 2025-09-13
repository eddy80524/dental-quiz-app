#!/usr/bin/env python3
"""
JSONデータのバックアップファイル整理スクリプト
- 各ファイルにつき最新のバックアップ1つのみを保持
- 古いバックアップは削除
"""

import os
import glob
import re
from datetime import datetime
from collections import defaultdict

def main():
    # データディレクトリのパス
    data_dir = "my_llm_app/data"
    
    # バックアップファイルを検索
    backup_pattern = os.path.join(data_dir, "*.backup*")
    backup_files = glob.glob(backup_pattern)
    
    if not backup_files:
        print("❌ バックアップファイルが見つかりません")
        return
    
    print(f"📂 見つかったバックアップファイル: {len(backup_files)}個")
    print("=" * 50)
    
    # ファイル別にバックアップをグループ化
    file_groups = defaultdict(list)
    
    for backup_file in backup_files:
        # ファイル名からベースファイル名を抽出
        base_name = re.sub(r'\.backup.*$', '', os.path.basename(backup_file))
        file_groups[base_name].append(backup_file)
    
    # 各ファイルグループについて処理
    total_kept = 0
    total_deleted = 0
    
    for base_name, backups in file_groups.items():
        print(f"\n📄 {base_name}")
        print(f"   バックアップ数: {len(backups)}個")
        
        if len(backups) <= 1:
            print(f"   ✅ 保持: {len(backups)}個（削除対象なし）")
            total_kept += len(backups)
            continue
        
        # ファイルの更新日時でソート（新しい順）
        backups_with_time = []
        for backup in backups:
            try:
                mtime = os.path.getmtime(backup)
                backups_with_time.append((backup, mtime))
            except OSError:
                print(f"   ⚠️  警告: {backup} の情報取得に失敗")
                continue
        
        # 更新日時でソート（新しい順）
        backups_with_time.sort(key=lambda x: x[1], reverse=True)
        
        if not backups_with_time:
            continue
        
        # 最新のバックアップを保持、それ以外は削除対象
        latest_backup = backups_with_time[0][0]
        old_backups = [backup for backup, _ in backups_with_time[1:]]
        
        print(f"   ✅ 保持: {os.path.basename(latest_backup)} "
              f"({datetime.fromtimestamp(backups_with_time[0][1]).strftime('%Y-%m-%d %H:%M:%S')})")
        total_kept += 1
        
        # 古いバックアップを削除
        for old_backup in old_backups:
            try:
                mtime = os.path.getmtime(old_backup)
                time_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                print(f"   🗑️  削除: {os.path.basename(old_backup)} ({time_str})")
                os.remove(old_backup)
                total_deleted += 1
            except OSError as e:
                print(f"   ❌ 削除失敗: {old_backup} - {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 処理結果:")
    print(f"   ✅ 保持されたバックアップ: {total_kept}個")
    print(f"   🗑️  削除されたバックアップ: {total_deleted}個")
    
    if total_deleted > 0:
        print(f"\n🎉 {total_deleted}個のバックアップファイルを削除しました！")
    else:
        print(f"\n✨ 削除対象のバックアップファイルはありませんでした")

if __name__ == "__main__":
    main()
