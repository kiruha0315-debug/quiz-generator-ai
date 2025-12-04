import streamlit as st
import google.generativeai as genai
import os
import re
import json
from PIL import Image
from io import BytesIO
import streamlit.components.v1 as components 

# --- 1. 初期設定とAPIキーの取得 ---

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

# 🔑 APIキーの取得はSecrets/環境変数からのみ行う（ユーザーから見えないようにするため）
try:
    API_KEY = os.environ.get("GEMINI_API_KEY") 
    
    if not API_KEY and 'GEMINI_API_KEY' in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]

    if API_KEY:
        genai.configure(api_key=API_KEY)
        api_key_valid = True
    else:
        api_key_valid = False
        # ユーザーには見えないようにサイドバーで警告
        st.sidebar.error("⚠️ APIキーが設定されていません。")

except Exception as e:
    api_key_valid = False
    st.sidebar.error(f"API設定エラー: {e}")

# 🔑 管理者モードのチェック（設定者向けデバッグ情報）
is_admin = st.query_params.get("admin") == "true"

if is_admin:
    st.sidebar.header("🔑 管理者設定モード")
    st.sidebar.write("このパネルは、URLクエリパラメータ`?admin=true`が設定されている場合にのみ表示されます。")
    if not api_key_valid:
        st.sidebar.error("Gemini APIキーがSecretsに設定されていません。")
    else:
        st.sidebar.success("Gemini API設定OKです。")

# --- 2. ユーザー入力エリア ---

st.subheader("ステップ1: 教材の入力方式と教科の選択")

input_method = st.radio(
    "教材の入力方式を選択してください",
    ('テキスト貼り付け', 'ファイルアップロード (PDF/TXT)', '写真アップロード (JPG/PNG)')
)

num_questions = st.number_input("生成する問題数", min_value=1, max_value=20, value=5)

selected_subject = st.selectbox(
    "科目を選択してください",
    ('ランダム/一般教養', '歴史・地理', '科学・技術 (理科)', '文学・言語 (国語/英語)', '経済・社会')
)

text_input = ""
uploaded_file = None
image_part = None

if input_method == 'テキスト貼り付け':
    text_input = st.text_area(
        "ここに教科書や資料の本文を貼り付けてください（100字以上推奨）",
        height=300
    )
    if not text_input:
        st.info("テキストを貼り付けてください。")

elif input_method == 'ファイルアップロード (PDF/TXT)':
    uploaded_file = st.file_uploader("TXTファイルをアップロードしてください", type=['txt'])
    if uploaded_file:
        if uploaded_file.type == 'text/plain':
            text_input = uploaded_file.read().decode('utf-8')
            st.success(f"{uploaded_file.name} を読み込みました。")
        else:
            st.warning("現在はTXTファイルのみ対応しています。PDFからの直接テキスト抽出は未実装です。")
    if not text_input:
        st.info("TXTファイルをアップロードしてください。")

elif input_method == '写真アップロード (JPG/PNG)':
    uploaded_file = st.file_uploader("教科書の写真をアップロードしてください", type=['jpg', 'jpeg', 'png'])
    if uploaded_file:
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption='アップロードされた教材画像', width=300)
            image_part = image
            st.info("画像をAIに渡し、内容を読み取らせます。")
        except Exception as e:
            st.error(f"画像の読み込みに失敗しました: {e}")

if not text_input and not image_part:
    st.session_state.quiz_data = None
    st.session_state.user_answers = {}


# --- 3. 問題生成ロジック ---

if 'quiz_data' not in st.session_state:
    st.session_state.quiz_data = None
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}

if st.button("問題を生成する"):
    if not api_key_valid:
        st.error("APIキーが設定されていないため、問題を生成できません。")
        st.stop()

    if not text_input and not image_part:
        st.error("教材（テキストまたは画像）を入力してください。")
        st.stop()
    
    if input_method == 'テキスト貼り付け' and len(text_input) < 100:
        st.error("テキストが短すぎます。100字以上の文章を貼り付けてください。")
        st.stop()

    # --- 教科ごとの問題形式ルールを定義 ---
    if selected_subject == '歴史・地理':
        problem_style_instruction = "問題タイプは、「fill_in_the_blank」（穴埋め）を50%、「descriptive」（記述式）を30%、「meaning」（語句の意味）を20%の比率で混合してください。歴史的な事実や年代、地名に焦点を当ててください。"
    elif selected_subject == '科学・技術 (理科)':
        problem_style_instruction = "問題タイプは、「multiple_choice」（5択）を70%、「descriptive」（記述式）を30%の比率で混合してください。物理法則や化学反応、定義の理解度を問う問題に焦点を当ててください。選択肢は誤解しやすいものが望ましいです。"
    elif selected_subject == '文学・言語 (国語/英語)':
        problem_style_instruction = "問題タイプは、「meaning」（語句の意味）を50%、「descriptive」（記述式：和訳、表現の意図など）を50%の比率で混合してください。文法や表現技法、単語の意味に焦点を当ててください。"
    elif selected_subject == '経済・社会':
        problem_style_instruction = "問題タイプは、「descriptive」（記述式：定義、影響、仕組み）を60%、「multiple_choice」（5択：統計や法律）を40%の比率で混合してください。社会の仕組みや経済原則の理解度を問う問題に焦点を当ててください。"
    else:
        problem_style_instruction = "問題タイプは、「multiple_choice」（5択）、「descriptive」（記述式）、「fill_in_the_blank」（穴埋め）、「meaning」（語句の意味）を均等に混ぜて生成してください。"
    
    # --- AIへの命令（プロンプト）を厳密に定義 ---
    system_prompt = f"""
    あなたはプロの教育コンテンツ作成AIです。
    以下の教材の内容を分析し、**{selected_subject}** の教科として最適な問題セットを{num_questions}問生成してください。

    **【問題形式指示】**
    {problem_style_instruction}

    【重要ルール】
    1. 各問題には、必ず type (multiple_choice, descriptive, fill_in_the_blank, meaning のいずれか)、question、そして explanation（解説）を含むこと。
    2. 'multiple_choice' の場合は、options配列（正答1つ、不正解3つ、計4つ）を必ず含むこと。
    3. 'descriptive', 'fill_in_the_blank', 'meaning' の場合は、'correct_answer' フィールドを必ず含み、'options'配列は不要です。
    4. 出力は、以下のJSON形式に**厳密に従って**ください。余計な説明や前置きは一切含めないでください。

    {{
      "questions": [
        {{
          "id": 1,
          "type": "multiple_choice",
          "question": "質問文",
          "options": [
            {{"text": "選択肢A", "is_correct": false}},
          ],
          "explanation": "解説文"
        }},
        //... {num_questions}問
      ]
    }}
    """
    
    content_list = [system_prompt]
    
    if image_part:
        content_list.append(image_part)
        content_list.append("上記の画像の内容を読み取り、以下の指示に従って問題を生成してください。")
    elif text_input:
        content_list.append(f"【入力テキスト】\n\n{text_input}")
    
    
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        with st.spinner(f"📝 {selected_subject}のルールに基づいて{num_questions}問を生成中..."):
            response = model.generate_content(
                content_list, 
                generation_config={"response_mime_type": "application/json"} 
            )

            quiz_data = response.text
            
            match = re.search(r'\{.*\}', quiz_data, re.DOTALL)
            if match:
                json_string = match.group(0)
                st.session_state.quiz_data = json.loads(json_string)
                st.session_state.user_answers = {} 
            else:
                st.error("AIからのレスポンスがJSON形式ではありませんでした。")
                st.text(quiz_data)
                st.session_state.quiz_data = None
            
    except Exception as e:
        st.error(f"問題生成中にエラーが発生しました: {e}")
        st.session_state.quiz_data = None


# --- 4. 結果表示エリア ---

if st.session_state.quiz_data:
    questions = st.session_state.quiz_data.get("questions", [])
    st.header(f"生成された問題 ({len(questions)}問)")
    
    for i, q in enumerate(questions):
        q_type = q.get("type", "unknown") 
        
        q_title_map = {
            "multiple_choice": "5択問題",
            "descriptive": "記述式問題",
            "fill_in_the_blank": "穴埋め問題",
            "meaning": "語句の意味問題"
        }
        display_title = q_title_map.get(q_type, "その他の問題")
        
        st.markdown(f"### 第{i+1}問: 【{display_title}】")
        st.markdown(f"**{q.get('question', '問題文が見つかりません')}**")

        if q_type == "multiple_choice":
            options = [opt.get("text") for opt in q.get("options", []) if opt.get("text")]
            user_choice = st.radio(
                "選択してください:",
                options=options,
                key=f"q{i}",
                index=None
            )
            st.session_state.user_answers[f"q{i}"] = user_choice

            if user_choice:
                correct_option = next((opt.get("text") for opt in q.get("options", []) if opt.get("is_correct")), None)
                
                if correct_option and user_choice == correct_option:
                    st.success("✅ 正解です！")
                elif correct_option:
                    st.error(f"❌ 不正解です。")
            
        else:
            user_input = st.text_input(
                "あなたの解答を入力してください",
                key=f"q{i}_input"
            )
            st.session_state.user_answers[f"q{i}"] = user_input
            
            if st.session_state.user_answers.get(f"q{i}"):
                st.info("⚠️ この形式は自己採点です。正答を確認してください。")
            
        with st.expander("👉 正答と解説を見る"):
            if q_type != "multiple_choice":
                st.markdown(f"**【期待される正答】** {q.get('correct_answer', '正答データなし')}")
            st.write(q.get('explanation', '解説データなし'))
            
        st.markdown("---")


    if st.button("最終スコアを見る", key="final_score_btn"):
        correct_count = 0
        total_mcq = 0
        
        for i, q in enumerate(questions):
            if q.get("type") == "multiple_choice":
                total_mcq += 1
                user_choice = st.session_state.user_answers.get(f"q{i}")
                
                if user_choice:
                    correct_option = next((opt.get("text") for opt in q.get("options", []) if opt.get("is_correct")), None)
                    if correct_option and user_choice == correct_option:
                        correct_count += 1

        if total_mcq > 0:
            st.balloons()
            st.subheader("✨ 最終スコア（5択問題のみ自動採点） ✨")
            st.metric(
                label="5択問題 正解数", 
                value=f"{correct_count}/{total_mcq}問"
            )
            st.success(f"正解率: {(correct_count/total_mcq)*100:.1f}%")
            st.info("記述式・穴埋め・意味問題は自動採点に含まれていません。")
        else:
            st.info("5択問題が生成されなかったため、自動採点スコアはありません。")
