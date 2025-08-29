#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LaTeX PDF生成の単体テスト
"""

import subprocess
import os
import uuid

def test_simple_latex():
    """シンプルなLaTeX文書のテスト"""
    
    # 超シンプルなテスト用LaTeX
    test_content = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[top=25mm,bottom=25mm,left=20mm,right=20mm]{geometry}

\title{Test Document}
\author{Test}
\date{\today}

\begin{document}
\maketitle

\section{Test Section}
This is a test document.

\subsection{Test Question}
What is 2 + 2?

A. 3
B. 4
C. 5

Answer: B

\end{document}
"""
    
    output_dir = "/tmp"
    unique_id = str(uuid.uuid4())[:8]
    base_name = f"test_{unique_id}"
    tex_file = os.path.join(output_dir, f"{base_name}.tex")
    pdf_file = os.path.join(output_dir, f"{base_name}.pdf")
    
    print(f"📄 テストファイル: {tex_file}")
    
    # LaTeXファイルを作成
    with open(tex_file, 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print(f"✅ LaTeXファイル作成完了: {os.path.getsize(tex_file)} バイト")
    
    # platexでコンパイル
    try:
        print("🔧 platexでコンパイル中...")
        result = subprocess.run(
            ["platex", "-halt-on-error", "-output-directory", output_dir, os.path.basename(tex_file)],
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ platexコンパイル成功")
            
            # DVIからPDFに変換
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
                    print(f"🎉 PDF生成成功！サイズ: {pdf_size} バイト")
                    print(f"📄 生成されたPDF: {pdf_file}")
                    return True
                else:
                    print(f"❌ DVI → PDF 変換失敗: {dvipdf_result.stderr}")
                    return False
            else:
                print("❌ DVIファイルが見つかりません")
                return False
        else:
            print(f"❌ platexコンパイル失敗: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_simple_latex()
    if success:
        print("✅ LaTeX環境テスト成功")
    else:
        print("❌ LaTeX環境テスト失敗")
