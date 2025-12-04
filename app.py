import streamlit as st
import google.generativeai as genai
import os
import re
import json
from PIL import Image
from io import BytesIO
import streamlit.components.v1 as components 

# --- 1. 初期設定とAPIキーの取得 ---

# 【重要】カスタムCSSは削除しました。UI非表示は外部HPのiframeで行います。

st.set_page_config(page_title="教材理解度テスト自動生成AI", layout="wide")

st.title("📚 教材理解度テスト自動生成AI")

# --- 広告エリア：タイトル直下に配置 ---

# 1つ目の広告 (target="_blank" を追加済み)
ad_html_code_1 = """
<div style="text-align: center; margin: 5px 0 10px 0;">
    <a href="https://px.a8.net/svt/ejp?a8mat=45K5P9+9SGMWI+4GDM+601S1" rel="nofollow" target="_blank">
    <img border="0" width="320" height="50" alt="" src="https://www28.a8.net/svt/bgt?aid=251203293592&wid=001&eno=01&mid=s00000020785001008000&mc=1"></a>
    <img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=45K5P9+9SGMWI+4GDM+601S1" alt="">
</div>
"""

# 2つ目の広告 (target="_blank" を追加済み)
ad_html_code_2 = """
<div style="text-align: center; margin: 10px 0;">
    <a href="https://px.a8.net/svt/ejp?a8mat=45K5P9+A4YQLU+2KSK+61C2P" rel="nofollow" target="_blank">
    <img border="0" width="350" height="240" alt="" src="https://www20.a8.net/svt/bgt?aid=251203293613&wid=001&eno=01&mid=s00000012026001014000&mc=1"></a>
    <img border="0" width="1" height="1" src="https://www18.a8.net/0.gif?a8mat=45K5P9+A4YQLU+2KSK+61C2P" alt="">
</div>
"""
# components.htmlを使って広告を表示
components.html(ad_html_code_1 + ad_html_code_2, height=320)

st.markdown("---") # 広告とアプリ本体の区切り

st.markdown("貼り付けたテキストやアップロードした写真から、**教科の特性**に合わせた問題セットを自動で生成します。")

# 🔑 APIキーの取得はSecrets/環境変数からのみ行う（ユーザーからは見えない）
try:
    API_KEY = os.environ.get("GEMINI_API_KEY") 
    
    if not API_KEY and 'GEMINI_API_KEY' in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]

    if API_KEY:
        genai.configure(api_key=API_KEY)
        api_key_valid = True
    else:
        api_key_valid = False
        # 管理者モード以外では見えないサイドバーに警告を出す
        st.sidebar.error("⚠️ APIキーが設定されていません。")

except Exception as e:
    api_key_valid = False
    st.sidebar.error(f"API設定エラー: {e}")

# 🔑 管理者モードのチェック（設定者向けデバッグ情報のみ）
is_admin = st.query_params.get("admin") == "true"

if is_admin:
    # st.sidebarはiframeで埋め込む際に空白になるため、デバッグ情報のみ表示
    st.sidebar.header("🔑 管理者設定モード")
    st.sidebar.write("このパネルは、URLクエリパラメータ`?admin=true`が設定されている場合にのみ表示されます。")
    if not api_key_valid:
        st.sidebar.error("Gemini APIキーがSecretsに設定されていません。")
    else:
        st.sidebar.success("Gemini API設定OKです。")

# --- 2. ユーザー入力エリア ---

st.subheader("ステップ1: 📚 問題の元となる教材を入力してください")

# ---------------------------------------------
# 1. 教材の入力方式の選択
# ---------------------------------------------
st.markdown("#### 1-A. 教材の入力方式を選ぶ")
input_method = st.radio(
    "問題を生成したい教材を、以下のいずれかの方法で入力してください:",
    ('テキスト貼り付け', 'ファイルアップロード (TXTのみ)', '写真アップロード (JPG/PNG)')
)
st.markdown("---") # 区切り線

# 選択された方式に応じた入力フォームの表示
text_input = ""
uploaded_file = None
image_part = None

if input_method == 'テキスト貼り付け':
    text_input = st.text_area(
        "📝 教科書や資料の本文をここに貼り付けてください（100字以上推奨）",
        height=300
    )
    if not text_input:
        st.info("↑ここに文章を貼り付けたら、ステップ1-Bに進んでください。")

elif input_method == 'ファイルアップロード (TXTのみ)':
    uploaded_file = st.file_uploader("📄 TXTファイルをアップロードしてください", type=['txt'])
    if uploaded_file:
        if uploaded_file.type == 'text/plain':
            text_input = uploaded_file.read().decode('utf-8')
            st.success(f"✅ {uploaded_file.name} のテキストを読み込みました。")
        else:
            st.warning("⚠️ 現在はTXTファイルのみに対応しています。")
    if not text_input:
        st.info("↑TXTファイルをアップロードしたら、ステップ1-Bに進んでください。")

elif input_method == '写真アップロード (JPG/PNG)':
    uploaded_file = st.file_uploader("📷 教科書やプリントの写真をアップロードしてください", type=['jpg', 'jpeg', 'png'])
    if uploaded_file:
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption='アップロードされた教材画像', width=300)
            image_part = image
            st.success("✅ 画像を読み込みました。AIが画像の内容を分析します。")
        except Exception as e:
            st.error(f"画像の読み込みに失敗しました: {e}")
    if not uploaded_file:
        st.info("↑画像をアップロードしたら、ステップ1-Bに進んでください。")

if not text_input and not image_part:
    st.session_state.quiz_data = None
    st.session_state.user_answers = {}
    
st.markdown("---") 

# ---------------------------------------------
# 2. 教科と問題数の選択
# ---------------------------------------------
st.markdown("#### 1-B. 問題のバランスと数を決める")

# 教科の選択
st.markdown("💡 **重要**: 教科を選ぶと、**
