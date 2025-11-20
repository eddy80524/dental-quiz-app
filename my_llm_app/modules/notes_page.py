import streamlit as st
from modules.notes_manager import NotesManager
from utils import ALL_QUESTIONS

def render_notes_page():
    """学習メモ閲覧ページ"""
    st.title("📚 学習メモ・振り返り")
    
    uid = st.session_state.get("uid")
    if not uid:
        st.warning("メモ機能を利用するにはログインが必要です。")
        return

    # 全メモを取得
    with st.spinner("メモを読み込み中..."):
        all_notes = NotesManager.get_all_user_notes(uid)

    if not all_notes:
        st.info("まだメモがありません。演習中に「メモ・振り返り」から記録を追加してみましょう！")
        return

    # フィルタリング機能
    search_query = st.text_input("🔍 メモを検索", placeholder="キーワードを入力...")

    st.divider()

    count = 0
    for note_entry in all_notes:
        qid = note_entry.get("question_id")
        notes = note_entry.get("notes", [])
        last_updated = note_entry.get("last_updated", "")

        # 問題情報を取得
        question_data = next((q for q in ALL_QUESTIONS if q.get("number") == qid), None)
        
        # 検索フィルタ
        if search_query:
            query = search_query.lower()
            # メモ内容、問題番号、問題文で検索
            note_content = " ".join([n.get("content", "") for n in notes]).lower()
            q_text = question_data.get("question", "") if question_data else ""
            
            if (query not in qid.lower() and 
                query not in note_content and 
                query not in q_text.lower()):
                continue

        count += 1
        
        with st.expander(f"📝 {qid} (更新: {last_updated[:16]})", expanded=False):
            # 問題文の表示（コンテキストとして）
            if question_data:
                st.markdown(f"**問題:** {question_data.get('question', '')[:100]}...")
            
            # メモの表示
            for i, note in enumerate(notes):
                NotesManager.render_note_display(note)
                
                # 削除ボタン
                col1, col2 = st.columns([6, 1])
                with col2:
                    if st.button("削除", key=f"del_note_page_{qid}_{i}"):
                        if NotesManager.delete_note(uid, qid, i):
                            st.success("削除しました")
                            st.rerun()

    if count == 0 and search_query:
        st.warning("検索結果が見つかりませんでした。")
