import streamlit_authenticator as stauth

# ここにテスト用のパスワードを入力
password_to_hash = 'Chibieito80524' 

# ★★★ 修正点：新しい使い方 ★★★
hasher = stauth.Hasher()
hashed_password = hasher.hash(password_to_hash)

print("以下のハッシュ化されたパスワードをコピーしてください:")
print(hashed_password)