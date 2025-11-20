# グラフ分析タブの刷新プラン

## 📋 現状分析

### 現在のグラフ分析タブの構成
1. **日々の学習量（過去90日間）** - 棒グラフ ✅ 良好
2. **学習レベル別分布** - 棒グラフ ✅ 良好
3. **科目別進捗率** - 横棒グラフ
4. **科目別平均正答率** - 横棒グラフ

### 問題点
- 科目別の進捗率と正答率が **別々のグラフ** で表示されているため、科目間の比較や優先順位の判断が難しい
- どの科目が「進捗は高いが正答率が低い（弱点）」なのか、パッと見で分からない
- グラフが縦に長くなり、スクロールが必要

---

## 🎯 提案: 科目パフォーマンスマトリックス

### コンセプト
**進捗率（X軸） × 正答率（Y軸）の散布図** で、各科目を一目で評価できるようにする。

### ビジュアル仕様

#### 軸の定義
- **X軸（横）**: 進捗率 (0-100%) - その科目の問題をどれだけ学習したか
- **Y軸（縦）**: 正答率 (0-100%) - その科目の問題をどれだけ正しく答えられているか

#### バブル（プロット点）の仕様
- **サイズ**: 科目の問題数（大きいほど重要度が高い）
- **色**: 科目名（または弱点スコアでグラデーション）
- **ラベル**: 科目名を直接表示

#### インタラクティブ機能
- **ホバー情報**:
  - 科目名
  - 進捗率: XX% (学習済み/全体)
  - 正答率: XX% (正解/試行)
  - 問題数: XX問
- **クリック**: その科目の問題リストにジャンプ（オプション）

### 4象限による分析

```
          正答率 (%)
            100|
               |    🟢 強み           🌟 マスター
               |   (要継続)        (完璧!)
            80%|━━━━━━━━━━━━━━━━━━━━━━━
               |
            50%|━━━━━━━━━━━━━━━━━━━━━━━
               |    🔵 未着手         ⚠️ 弱点
               |   (新規)          (要復習!)
             0 |________________________
               0      50%           100%
                     進捗率 (%)
```

#### 象限の解釈
1. **右上（高進捗 × 高正答率）**: ✅ **マスター** - 完璧な科目
2. **左上（低進捗 × 高正答率）**: 📈 **ポテンシャル** - 得意分野、もっと問題を解くべき
3. **右下（高進捗 × 低正答率）**: ⚠️ **弱点** - 復習が必要、最優先
4. **左下（低進捗 × 低正答率）**: 🆕 **未着手** - これから学習する分野

---

## 💻 実装計画

### Phase 1: データ準備

#### `render_graph_analysis_tab_perfect` の修正箇所
**ファイル**: `my_llm_app/modules/search_page.py`

1. **データマージ**:
```python
# 既存のprogress_summaryとaccuracy_summaryをマージ
combined_df = progress_summary.merge(
    accuracy_summary[['subject_display', 'accuracy_pct', 'total_attempts']], 
    on='subject_display', 
    how='outer'
)

# NaN処理（正答率データがない科目は0%とする）
combined_df['accuracy_pct'] = combined_df['accuracy_pct'].fillna(0)
combined_df = combined_df.dropna(subset=['progress_pct'])  # 進捗率がない科目は除外
```

### Phase 2: 散布図の作成

```python
import plotly.graph_objects as go

fig = go.Figure()

# バブルチャートを追加
fig.add_trace(go.Scatter(
    x=combined_df['progress_pct'],
    y=combined_df['accuracy_pct'],
    mode='markers+text',
    marker=dict(
        size=combined_df['total_questions'],
        sizemode='diameter',
        sizeref=2.*max(combined_df['total_questions'])/(40.**2),  # サイズ調整
        color=combined_df.index,  # 科目ごとに色分け
        colorscale='Viridis',
        showscale=False,
        line=dict(width=1, color='white')
    ),
    text=combined_df['subject_display'],
    textposition='top center',
    textfont=dict(size=10),
    hovertemplate=(
        '<b>%{text}</b><br>' +
        '進捗率: %{x:.1f}% (%{customdata[0]}/%{customdata[1]}問)<br>' +
        '正答率: %{y:.1f}% (%{customdata[2]}/%{customdata[3]}回)<br>' +
        '<extra></extra>'
    ),
    customdata=combined_df[[
        'studied_questions', 'total_questions',
        'correct_attempts', 'total_attempts'
    ]].values
))

# 象限を示す補助線を追加
fig.add_hline(y=80, line_dash="dash", line_color="gray", opacity=0.5,
              annotation_text="合格ライン (80%)", annotation_position="right")
fig.add_vline(x=50, line_dash="dash", line_color="gray", opacity=0.5,
              annotation_text="進捗50%", annotation_position="top")

# レイアウト設定
fig.update_layout(
    title=f"{analysis_target} 科目別パフォーマンスマトリックス",
    xaxis=dict(
        title='進捗率 (%)',
        range=[-5, 105],
        showgrid=True,
        gridcolor='lightgray'
    ),
    yaxis=dict(
        title='正答率 (%)',
        range=[-5, 105],
        showgrid=True,
        gridcolor='lightgray'
    ),
    height=600,
    hovermode='closest',
    showlegend=False
)

st.plotly_chart(fig, use_container_width=True)
```

### Phase 3: 補足情報の追加

散布図の下に、各象限の科目リストを表示:

```python
st.markdown("### 📊 象限別の科目")

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### ⚠️ 要復習（高進捗×低正答率）")
    weak_subjects = combined_df[
        (combined_df['progress_pct'] >= 50) & 
        (combined_df['accuracy_pct'] < 80)
    ]['subject_display'].tolist()
    if weak_subjects:
        for subject in weak_subjects:
            st.markdown(f"- {subject}")
    else:
        st.info("該当なし")

with col2:
    st.markdown("#### 🌟 マスター（高進捗×高正答率）")
    master_subjects = combined_df[
        (combined_df['progress_pct'] >= 50) & 
        (combined_df['accuracy_pct'] >= 80)
    ]['subject_display'].tolist()
    if master_subjects:
        for subject in master_subjects:
            st.markdown(f"- {subject}")
    else:
        st.info("該当なし")
```

---

## 🎨 追加の可視化アイデア

### 1. 学習強度ヒートマップ
- X軸: 日付（過去30日）
- Y軸: 科目
- 色: その日のその科目の学習量

### 2. 忘却曲線の可視化
- SM-2アルゴリズムの次回復習予定日を基に、「復習が必要な問題数」の推移を予測

### 3. 弱点分野の詳細分析
- 間違えた問題の「出題年度」「問題タイプ（必修/一般/臨床）」の分布

### 4. 学習ペース予測
- 現在のペースで全科目をマスターするまでの予測日数

---

## ✅ 実装のメリット

1. **一目で弱点が分かる**: 右下の象限（高進捗×低正答率）の科目に注力すべき
2. **学習戦略の立案が容易**: 各象限に応じた学習アクションが明確
3. **視覚的に分かりやすい**: 2つの棒グラフを見比べる必要がなくなる
4. **問題数の重みづけ**: バブルサイズで重要な科目が視覚化される
5. **UI のコンパクト化**: 2つのグラフが1つになり、スクロールが減る

---

## 📅 実装スケジュール

### Step 1: データマージロジックの実装 (15分)
- `progress_summary` と `accuracy_summary` の結合

### Step 2: 散布図の作成 (30分)
- Plotly の `go.Scatter` を使用
- バブルサイズ、色、ホバー情報の設定

### Step 3: 補助線と象限ラベルの追加 (15分)
- `add_hline`, `add_vline` で象限を明示

### Step 4: 象限別科目リストの実装 (15分)
- 散布図の下に補足情報を追加

### Step 5: テスト & 調整 (15分)
- 実データでの動作確認
- レイアウトの微調整

**合計見積もり時間**: 約1.5時間

---

## 🚀 次のステップ

1. ✅ プランのレビュー
2. 実装開始
3. テスト & フィードバック
4. 本番環境への展開
