#!/usr/bin/env python3
"""
問題データベースの内訳分析スクリプト
年度別、科目別、難易度別の問題数を確認
"""

import sys
import os
from collections import Counter, defaultdict
import re

# Firebase Admin SDK を直接使用
import firebase_admin
from firebase_admin import credentials, firestore

class ProblemAnalyzer:
    """問題データベース分析クラス"""
    
    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """Firebase Admin SDKを初期化"""
        try:
            if firebase_admin._apps:
                self.db = firestore.client()
                return
            
            cred = credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {
                'projectId': 'dent-ai-4d8d8'
            })
            
            self.db = firestore.client()
            print("✅ Firebase接続完了")
            
        except Exception as e:
            print(f"❌ Firebase初期化エラー: {e}")
            raise e
    
    def analyze_all_problems(self):
        """全問題データを分析"""
        try:
            print("📊 全問題データを分析中...")
            
            # study_cardsから全ユニークな問題を取得
            cards_ref = self.db.collection('study_cards')
            cards_docs = cards_ref.get()
            
            # 問題IDごとにデータを集計
            unique_problems = {}
            user_problem_pairs = []
            
            for doc in cards_docs:
                card_data = doc.to_dict()
                question_id = card_data.get('question_id')
                uid = card_data.get('uid')
                metadata = card_data.get('metadata', {})
                
                if question_id:
                    user_problem_pairs.append((uid, question_id))
                    
                    # ユニークな問題として記録
                    if question_id not in unique_problems:
                        unique_problems[question_id] = {
                            'question_id': question_id,
                            'subject': metadata.get('subject', '不明'),
                            'difficulty': metadata.get('difficulty', 'normal'),
                            'original_level': metadata.get('original_level', 0),
                            'user_count': 0,
                            'year': self._extract_year_from_id(question_id),
                            'exam_type': self._determine_exam_type(question_id)
                        }
                    
                    unique_problems[question_id]['user_count'] += 1
            
            print(f"✅ 分析完了: ユニーク問題数 {len(unique_problems)}, 総カードエントリ数 {len(user_problem_pairs)}")
            
            return {
                'unique_problems': unique_problems,
                'total_card_entries': len(user_problem_pairs),
                'user_problem_pairs': user_problem_pairs
            }
            
        except Exception as e:
            print(f"❌ 分析エラー: {e}")
            return {}
    
    def _extract_year_from_id(self, question_id):
        """問題IDから年度を抽出"""
        # 問題IDのパターンを分析（例: 100A1, 95B10, 118A1など）
        match = re.match(r'(\d+)', question_id)
        if match:
            year_part = int(match.group(1))
            
            # 年度の推定ロジック
            if year_part >= 95 and year_part <= 99:
                return f"19{year_part}"  # 1995-1999
            elif year_part >= 100 and year_part <= 125:
                return f"20{year_part - 100:02d}"  # 2000-2025
            elif year_part >= 1995:
                return str(year_part)  # 直接年号
            else:
                return "不明"
        return "不明"
    
    def _determine_exam_type(self, question_id):
        """問題IDから試験種別を判定"""
        # 歯科国試の一般的なパターン
        if re.match(r'\d+[A-D]\d+', question_id):
            return "歯科国試"
        elif re.match(r'[A-Z]+\d+', question_id):
            return "学士試験"
        else:
            return "その他"
    
    def generate_statistics(self, analysis_data):
        """統計情報を生成"""
        unique_problems = analysis_data['unique_problems']
        
        # 科目別統計
        subject_stats = Counter()
        year_stats = Counter()
        exam_type_stats = Counter()
        difficulty_stats = Counter()
        user_distribution = Counter()
        
        for problem_data in unique_problems.values():
            subject_stats[problem_data['subject']] += 1
            year_stats[problem_data['year']] += 1
            exam_type_stats[problem_data['exam_type']] += 1
            difficulty_stats[problem_data['difficulty']] += 1
            user_distribution[problem_data['user_count']] += 1
        
        return {
            'unique_problem_count': len(unique_problems),
            'total_card_entries': analysis_data['total_card_entries'],
            'subject_distribution': dict(subject_stats),
            'year_distribution': dict(year_stats),
            'exam_type_distribution': dict(exam_type_stats),
            'difficulty_distribution': dict(difficulty_stats),
            'user_distribution': dict(user_distribution),
            'most_common_subjects': subject_stats.most_common(10),
            'recent_years': {year: count for year, count in year_stats.items() if year.startswith('20')},
            'replication_factor': analysis_data['total_card_entries'] / len(unique_problems) if unique_problems else 0
        }
    
    def suggest_problem_set_definition(self, stats):
        """適切な問題セット定義を提案"""
        print("\n💡 問題セット定義の提案:")
        
        total_unique = stats['unique_problem_count']
        replication = stats['replication_factor']
        
        print(f"📊 現状分析:")
        print(f"  ユニーク問題数: {total_unique}")
        print(f"  総カードエントリ数: {stats['total_card_entries']}")
        print(f"  平均複製率: {replication:.1f}倍")
        
        # 年度別推奨セット
        recent_years = stats['recent_years']
        sorted_years = sorted(recent_years.items(), key=lambda x: x[0], reverse=True)
        
        print(f"\n📅 年度別問題数:")
        for year, count in sorted_years[:10]:
            print(f"  {year}年: {count}問")
        
        # 推奨問題セット
        print(f"\n🎯 推奨問題セット定義:")
        
        # 最新5年間
        latest_5_years = sum(count for year, count in sorted_years[:5])
        print(f"  最新5年間セット: {latest_5_years}問")
        
        # 最新10年間
        latest_10_years = sum(count for year, count in sorted_years[:10])
        print(f"  最新10年間セット: {latest_10_years}問")
        
        # 歯科国試のみ
        dental_exam_count = stats['exam_type_distribution'].get('歯科国試', 0)
        print(f"  歯科国試のみ: {dental_exam_count}問")
        
        # 科目別フィルタリング提案
        print(f"\n📚 主要科目:")
        for subject, count in stats['most_common_subjects'][:5]:
            print(f"  {subject}: {count}問")
        
        return {
            'latest_5_years': latest_5_years,
            'latest_10_years': latest_10_years,
            'dental_exam_only': dental_exam_count,
            'recommended_filters': {
                'years': [year for year, _ in sorted_years[:5]],
                'exam_types': ['歯科国試'],
                'exclude_subjects': ['その他', '不明'] if '不明' in stats['subject_distribution'] else []
            }
        }

def main():
    analyzer = ProblemAnalyzer()
    
    print("🔍 歯科国試問題データベース分析")
    print("=" * 70)
    
    # 全問題データを分析
    analysis_data = analyzer.analyze_all_problems()
    
    if not analysis_data:
        print("❌ データ分析に失敗しました")
        return
    
    # 統計情報を生成
    stats = analyzer.generate_statistics(analysis_data)
    
    # 結果表示
    print(f"\n📊 分析結果:")
    print(f"  ユニーク問題数: {stats['unique_problem_count']}")
    print(f"  総カードエントリ数: {stats['total_card_entries']}")
    print(f"  複製率: {stats['replication_factor']:.1f}倍")
    
    print(f"\n📚 科目別分布:")
    for subject, count in sorted(stats['subject_distribution'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {subject}: {count}問")
    
    print(f"\n🏥 試験種別分布:")
    for exam_type, count in stats['exam_type_distribution'].items():
        print(f"  {exam_type}: {count}問")
    
    print(f"\n📈 難易度分布:")
    for difficulty, count in stats['difficulty_distribution'].items():
        print(f"  {difficulty}: {count}問")
    
    # 問題セット定義の提案
    recommendations = analyzer.suggest_problem_set_definition(stats)

if __name__ == "__main__":
    main()
