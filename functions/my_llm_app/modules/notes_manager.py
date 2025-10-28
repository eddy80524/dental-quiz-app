"""
問題メモ管理モジュール（解答後のみ版）
"""
import streamlit as st
from typing import Dict, List, Optional
from datetime import datetime
from firestore_db import get_firestore_manager

class NotesManager:
    """問題メモの管理クラス（解答後のみ・テキスト + 画像対応）"""
    
    @staticmethod
    def get_question_notes(uid: str, question_id: str) -> List[Dict]:
        """問題のメモを取得"""
        try:
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                return []
            
            note_id = f"{uid}_{question_id}"
            notes_ref = firestore_manager.db.collection("question_notes").document(note_id)
            doc = notes_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                return data.get("notes", [])
            return []
        except Exception as e:
            print(f"メモ取得エラー: {e}")
            return []
    
    @staticmethod
    def upload_image_to_firebase(uid: str, question_id: str, image_file) -> Optional[str]:
        """画像をFirebase Storageにアップロード"""
        try:
            from firebase_admin import storage
            
            print(f"📸 画像アップロード開始: {image_file.name}")
            
            # バケット名を明示的に指定
            bucket = storage.bucket("dent-ai-4d8d8.appspot.com")
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_extension = image_file.name.split('.')[-1]
            storage_path = f"user_notes/{uid}/{question_id}/{timestamp}.{file_extension}"
            
            print(f"📁 保存パス: {storage_path}")
            
            # ファイルポインタを先頭に戻す
            image_file.seek(0)
            
            blob = bucket.blob(storage_path)
            blob.upload_from_file(image_file, content_type=image_file.type)
            
            print(f"✅ アップロード成功")
            
            blob.make_public()
            public_url = blob.public_url
            
            print(f"🔗 公開URL: {public_url}")
            
            return public_url
            
        except Exception as e:
            print(f"❌ 画像アップロードエラー: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def add_note(uid: str, question_id: str, content: str, images: List[str] = None) -> bool:
        """メモを追加（解答後のみ）"""
        try:
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                return False
            
            note_id = f"{uid}_{question_id}"
            notes_ref = firestore_manager.db.collection("question_notes").document(note_id)
            
            new_note = {
                "content": content,
                "images": images or [],
                "timestamp": datetime.now().isoformat(),
                "note_type": "rich"
            }
            
            doc = notes_ref.get()
            if doc.exists:
                data = doc.to_dict()
                notes = data.get("notes", [])
                notes.append(new_note)
                
                notes_ref.update({
                    "notes": notes,
                    "last_updated": datetime.now().isoformat()
                })
            else:
                notes_ref.set({
                    "uid": uid,
                    "question_id": question_id,
                    "notes": [new_note],
                    "last_updated": datetime.now().isoformat()
                })
            
            return True
        except Exception as e:
            print(f"メモ追加エラー: {e}")
            return False
    
    @staticmethod
    def update_note(uid: str, question_id: str, note_index: int, new_content: str) -> bool:
        """メモを更新"""
        try:
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                return False
            
            note_id = f"{uid}_{question_id}"
            notes_ref = firestore_manager.db.collection("question_notes").document(note_id)
            
            doc = notes_ref.get()
            if doc.exists:
                data = doc.to_dict()
                notes = data.get("notes", [])
                
                if 0 <= note_index < len(notes):
                    notes[note_index]["content"] = new_content
                    notes[note_index]["timestamp"] = datetime.now().isoformat()
                    
                    notes_ref.update({
                        "notes": notes,
                        "last_updated": datetime.now().isoformat()
                    })
                    return True
            return False
        except Exception as e:
            print(f"メモ更新エラー: {e}")
            return False
    
    @staticmethod
    def delete_note(uid: str, question_id: str, note_index: int) -> bool:
        """メモを削除"""
        try:
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                return False
            
            note_id = f"{uid}_{question_id}"
            notes_ref = firestore_manager.db.collection("question_notes").document(note_id)
            
            doc = notes_ref.get()
            if doc.exists:
                data = doc.to_dict()
                notes = data.get("notes", [])
                
                if 0 <= note_index < len(notes):
                    notes.pop(note_index)
                    
                    notes_ref.update({
                        "notes": notes,
                        "last_updated": datetime.now().isoformat()
                    })
                    return True
            return False
        except Exception as e:
            print(f"メモ削除エラー: {e}")
            return False
    
    @staticmethod
    def get_all_user_notes(uid: str) -> List[Dict]:
        """ユーザーの全メモを取得（修正版）"""
        try:
            firestore_manager = get_firestore_manager()
            if not firestore_manager:
                print("Firestore manager is None")
                return []
            
            notes_ref = firestore_manager.db.collection("question_notes")
            
            # uidフィールドでフィルター（order_byを削除してインデックス不要に）
            query = notes_ref.where("uid", "==", uid)
            
            all_notes = []
            docs = query.stream()
            
            for doc in docs:
                data = doc.to_dict()
                all_notes.append({
                    "question_id": data.get("question_id"),
                    "notes": data.get("notes", []),
                    "last_updated": data.get("last_updated")
                })
            
            # Pythonでソート（last_updatedの降順）
            all_notes.sort(key=lambda x: x.get("last_updated", ""), reverse=True)
            
            print(f"✅ 取得したメモ数: {len(all_notes)}")
            return all_notes
            
        except Exception as e:
            print(f"❌ 全メモ取得エラー: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    @staticmethod
    def render_note_display(note: Dict) -> None:
        """メモの表示（テキスト + 画像）"""
        content = note.get("content", "")
        images = note.get("images", [])
        timestamp = note.get("timestamp", "")
        
        st.markdown(f"**📅 {timestamp[:16]}**")
        
        if content:
            st.markdown(f"> {content}")
        
        if images:
            cols = st.columns(min(len(images), 3))
            for i, img_url in enumerate(images):
                with cols[i % 3]:
                    try:
                        st.image(img_url, use_container_width=True, caption=f"画像 {i+1}")
                    except Exception as e:
                        st.warning(f"画像の読み込みに失敗: {img_url}")
