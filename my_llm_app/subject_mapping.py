"""
歯科国家試験の正式な科目体系とマッピング

歯科国家試験の出題基準に基づく科目分類を定義し、
データ内の科目名との対応関係を管理する。
"""

# 歯科国家試験の正式な科目体系（2023年版出題基準準拠）
OFFICIAL_DENTAL_SUBJECTS = {
    # A領域: 歯科医学総論
    "歯科医学総論": [
        "人体の構造と機能",
        "歯・口腔・顎・顔面の構造と機能", 
        "病因・病態",
        "診査・検査",
        "治療"
    ],
    
    # B領域: 歯科医学各論
    "歯科医学各論": [
        "保存修復学",
        "歯内治療学", 
        "歯周病学",
        "口腔外科学",
        "歯科麻酔学",
        "小児歯科学",
        "矯正歯科学",
        "歯科補綴学",
        "歯科放射線学",
        "歯科理工学",
        "口腔衛生学"
    ],
    
    # C領域: 隣接医学
    "隣接医学": [
        "内科学",
        "外科学",
        "精神科学",
        "産婦人科学",
        "小児科学",
        "皮膚科学",
        "眼科学",
        "耳鼻咽喉科学",
        "放射線医学",
        "リハビリテーション医学",
        "麻酔科学"
    ],
    
    # D領域: 社会歯科学
    "社会歯科学": [
        "衛生学・公衆衛生学",
        "法医学",
        "関係法規"
    ]
}

# データ内の科目名から正式科目名へのマッピング
SUBJECT_MAPPING = {
    # 基礎医学系
    "解剖学": "人体の構造と機能",
    "組織学": "人体の構造と機能", 
    "生理学": "人体の構造と機能",
    "生化学": "人体の構造と機能",
    "薬理学": "人体の構造と機能",
    "病理学": "病因・病態",
    "微生物学": "病因・病態",
    "微生物学・免疫学": "病因・病態",
    "免疫学": "病因・病態",
    
    # 口腔系基礎
    "口腔解剖学": "歯・口腔・顎・顔面の構造と機能",
    "口腔組織学": "歯・口腔・顎・顔面の構造と機能",
    "口腔生理学": "歯・口腔・顎・顔面の構造と機能",
    "口腔生化学": "歯・口腔・顎・顔面の構造と機能",
    "口腔病理学": "病因・病態",
    
    # 歯科臨床系
    "保存修復学": "保存修復学",
    "歯内治療学": "歯内治療学",
    "歯周病学": "歯周病学", 
    "歯周治療学": "歯周病学",
    "口腔治療学": "歯周病学",  # 歯周治療を含む場合
    "口腔外科学": "口腔外科学",
    "口腔外科学1": "口腔外科学",
    "口腔外科学2": "口腔外科学",
    "歯科麻酔学": "歯科麻酔学",
    "小児歯科学": "小児歯科学",
    "矯正歯科学": "矯正歯科学",
    
    # 補綴系
    "歯科補綴学": "歯科補綴学",
    "クラウンブリッジ学": "歯科補綴学",
    "部分床義歯学": "歯科補綴学", 
    "全部床義歯学": "歯科補綴学",
    "有歯補綴咬合学": "歯科補綴学",
    "欠損歯列補綴咬合学": "歯科補綴学",
    "インプラント学": "歯科補綴学",
    "口腔インプラント": "歯科補綴学",
    
    # 歯科放射線・理工
    "歯科放射線学": "歯科放射線学",
    "歯科理工学": "歯科理工学",
    
    # 予防・衛生系
    "口腔衛生学": "口腔衛生学",
    "歯科衛生学": "口腔衛生学",
    "予防歯科学": "口腔衛生学",
    "衛生学": "衛生学・公衆衛生学",
    "公衆衛生学": "衛生学・公衆衛生学",
    "衛生学・公衆衛生学": "衛生学・公衆衛生学",
    
    # 隣接医学
    "内科学": "内科学",
    "外科学": "外科学", 
    "精神科学": "精神科学",
    "産婦人科学": "産婦人科学",
    "小児科学": "小児科学",
    "皮膚科学": "皮膚科学",
    "眼科学": "眼科学",
    "耳鼻咽喉科学": "耳鼻咽喉科学",
    "放射線医学": "放射線医学",
    "リハビリテーション医学": "リハビリテーション医学",
    "麻酔科学": "麻酔科学",
    
    # 社会歯科学
    "法医学": "法医学",
    "関係法規": "関係法規",
    "医事法制": "関係法規",
    "倫理学": "関係法規",  # 医療倫理として
    
    # その他の科目
    "化学": "人体の構造と機能",  # 基礎科学として
    "物理学": "人体の構造と機能",
    "数学": "人体の構造と機能",
    "統計学": "衛生学・公衆衛生学",
}

def get_standardized_subject(subject):
    """
    科目名を標準化して返す（表示用ではなく内部分類用）
    
    Args:
        subject (str): 元の科目名
        
    Returns:
        str: 標準化された科目名（内部使用のみ）
    """
    if not subject:
        return "その他"
    
    return SUBJECT_MAPPING.get(subject, subject)

def get_subject_domain(subject):
    """
    科目の出題基準ドメイン（A/B/C/D）を取得
    
    Args:
        subject (str): 元の科目名
        
    Returns:
        str: 出題基準ドメイン（A, B, C, D, その他）
    """
    standardized = get_standardized_subject(subject)
    
    # ドメインA: 歯科医学総論
    domain_a = ["口腔解剖学", "口腔組織発生学", "口腔生理学", "口腔生化学", "歯科理工学", "歯科薬理学", "口腔病理学", "口腔細菌学", "歯科放射線学"]
    
    # ドメインB: 歯科医学各論  
    domain_b = ["歯科保存学", "歯周病学", "歯科補綴学", "口腔外科学", "歯科矯正学", "小児歯科学", "歯科麻酔学"]
    
    # ドメインC: 隣接医学
    domain_c = ["全身管理・医学的緊急事態", "内科学", "外科学", "耳鼻咽喉科学", "眼科学", "皮膚科学", "精神医学", "小児科学", "産婦人科学", "整形外科学", "泌尿器科学", "脳神経外科学"]
    
    # ドメインD: 社会歯科学
    domain_d = ["衛生学・公衆衛生学", "歯科医療管理学", "法医学・法歯学", "医の倫理・歯科医師法"]
    
    if standardized in domain_a:
        return "A"
    elif standardized in domain_b:
        return "B"
    elif standardized in domain_c:
        return "C"
    elif standardized in domain_d:
        return "D"
    else:
        return "その他"

def get_subjects_by_domain(domain):
    """
    指定されたドメインに属する科目一覧を取得
    
    Args:
        domain (str): ドメイン（A, B, C, D）
        
    Returns:
        list: 該当する科目のリスト
    """
    if domain == "A":
        return ["口腔解剖学", "口腔組織発生学", "口腔生理学", "口腔生化学", "歯科理工学", "歯科薬理学", "口腔病理学", "口腔細菌学", "歯科放射線学"]
    elif domain == "B":
        return ["歯科保存学", "歯周病学", "歯科補綴学", "口腔外科学", "歯科矯正学", "小児歯科学", "歯科麻酔学"]
    elif domain == "C":
        return ["全身管理・医学的緊急事態", "内科学", "外科学", "耳鼻咽喉科学", "眼科学", "皮膚科学", "精神医学", "小児科学", "産婦人科学", "整形外科学", "泌尿器科学", "脳神経外科学"]
    elif domain == "D":
        return ["衛生学・公衆衛生学", "歯科医療管理学", "法医学・法歯学", "医の倫理・歯科医師法"]
    else:
        return []

def get_subject_category(subject: str) -> str:
    """
    科目のカテゴリ（A,B,C,D領域）を取得
    
    Args:
        subject: 標準化された科目名
        
    Returns:
        カテゴリ名
    """
    for category, subjects in OFFICIAL_DENTAL_SUBJECTS.items():
        if subject in subjects:
            return category
    return "その他"

def get_all_standardized_subjects():
    """
    すべての標準化された科目のリストを取得
    
    Returns:
        標準化された科目名のリスト
    """
    all_subjects = []
    for subjects in OFFICIAL_DENTAL_SUBJECTS.values():
        all_subjects.extend(subjects)
    return sorted(list(set(all_subjects)))

def analyze_subject_mapping(all_questions):
    """
    現在の問題データの科目マッピング状況を分析
    
    Args:
        all_questions: 全問題データ
        
    Returns:
        分析結果の辞書
    """
    original_subjects = set()
    standardized_subjects = set()
    unmapped_subjects = set()
    
    for q in all_questions:
        original = q.get("subject", "未分類")
        original_subjects.add(original)
        
        standardized = get_standardized_subject(original)
        standardized_subjects.add(standardized)
        
        if standardized == original and original not in SUBJECT_MAPPING:
            unmapped_subjects.add(original)
    
    return {
        "original_count": len(original_subjects),
        "standardized_count": len(standardized_subjects),
        "unmapped_subjects": sorted(list(unmapped_subjects)),
        "mapping_coverage": (len(original_subjects) - len(unmapped_subjects)) / len(original_subjects) * 100
    }
