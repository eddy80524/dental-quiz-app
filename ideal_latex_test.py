#!/usr/bin/env python3
"""
理想形LaTeXテンプレートのテスト（tcolorbox版）
"""

import subprocess
import os
import uuid

def test_ideal_latex_template():
    """理想形LaTeXテンプレート（tcolorbox使用）のテスト"""
    
    # テスト用の問題データ
    test_question = {
        "number": "115A77",
        "subject": "クラウンブリッジ学",
        "question": "40歳の女性。上顎左側歯列の咬み合わせの違和感を主訴として来院した。",
        "choices": "A. ア | B. イ | C. ウ | D. エ | E. オ",
        "choices_raw": ["ア", "イ", "ウ", "エ", "オ"],
        "answer": "C",
        "is_hisshu": False
    }
    
    # 理想形LaTeXテンプレート（tcolorbox使用）
    latex_content = r"""
\documentclass[11pt,a4paper,uplatex]{jsarticle}
\usepackage[utf8]{inputenc}
\usepackage[dvipdfmx]{hyperref}
\hypersetup{colorlinks=true,citecolor=blue,linkcolor=blue}
\usepackage{xcolor}
\definecolor{lightgray}{HTML}{F9F9F9}
\definecolor{questionbg}{HTML}{E6F3FF}
\definecolor{questionframe}{HTML}{0066CC}
\renewcommand{\labelitemi}{・}
\def\labelitemi{・}
\usepackage{tcolorbox}
\tcbuselibrary{breakable, skins, theorems}
\usepackage[top=30truemm,bottom=30truemm,left=25truemm,right=25truemm]{geometry}
\renewcommand{\labelenumii}{\theenumii}
\renewcommand{\theenumii}{\alph{enumi}}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage{graphicx}

% カスタム問題ボックス環境
\newtcolorbox{questionbox}[1][]{
    enhanced,
    breakable,
    colback=questionbg,
    colframe=questionframe,
    title=問題 #1,
    fonttitle=\bfseries,
    attach boxed title to top left={yshift=-3mm,yshifttext=-1mm},
    boxed title style={size=small,colback=questionframe},
    before skip=10pt,
    after skip=10pt
}

\begin{document}

\begin{questionbox}[115A77]
\textbf{科目:} クラウンブリッジ学

\vspace{0.5em}
\textbf{問題:}

40歳の女性。上顎左側歯列の咬み合わせの違和感を主訴として来院した。

\textbf{選択肢:}
\begin{enumerate}
    \item[A.] ア
    \item[B.] イ
    \item[C.] ウ
    \item[D.] エ
    \item[E.] オ
\end{enumerate}

\textbf{正解:} C

\end{questionbox}

\end{document}
"""
    
    # 一意なファイル名を生成
    unique_id = str(uuid.uuid4())[:8]
    base_name = f"ideal_test_{unique_id}"
    output_dir = "/tmp"
    
    tex_file = os.path.join(output_dir, f"{base_name}.tex")
    pdf_file = os.path.join(output_dir, f"{base_name}.pdf")
    
    print(f"📄 理想形テストファイル: {tex_file}")
    
    # LaTeXファイルを作成
    with open(tex_file, 'w', encoding='utf-8') as f:
        f.write(latex_content)
    
    file_size = os.path.getsize(tex_file)
    print(f"✅ 理想形LaTeXファイル作成完了: {file_size} バイト")
    
    try:
        # uplatexでコンパイル
        print("🔧 uplatex（理想形）でコンパイル中...")
        result = subprocess.run(
            ["uplatex", "-halt-on-error", "-output-directory", output_dir, os.path.basename(tex_file)],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✅ uplatex（理想形）コンパイル成功")
            
            # DVI → PDF 変換
            dvi_file = os.path.join(output_dir, f"{base_name}.dvi")
            if os.path.exists(dvi_file):
                print("📄 DVI → PDF 変換中...")
                dvipdf_result = subprocess.run(
                    ["dvipdfmx", "-o", f"{base_name}.pdf", f"{base_name}.dvi"],
                    cwd=output_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if dvipdf_result.returncode == 0 and os.path.exists(pdf_file):
                    pdf_size = os.path.getsize(pdf_file)
                    print(f"🎉 理想形PDF生成成功！サイズ: {pdf_size} バイト")
                    print(f"📄 生成されたPDF: {pdf_file}")
                    return True
                else:
                    print(f"❌ DVI → PDF 変換失敗: {dvipdf_result.stderr}")
                    return False
            else:
                print("❌ DVIファイルが生成されませんでした")
                return False
        else:
            print(f"❌ uplatex（理想形）コンパイル失敗:")
            print(result.stderr[:500])
            return False
            
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

if __name__ == "__main__":
    print("🧪 理想形LaTeX環境テスト開始")
    print("=" * 50)
    
    if test_ideal_latex_template():
        print("✅ 理想形LaTeX環境テスト成功")
        print("🎯 tcolorboxを使った美しいPDFが生成できます！")
    else:
        print("❌ 理想形LaTeX環境テスト失敗")
        print("⚠️ tcolorboxパッケージの問題の可能性があります")
