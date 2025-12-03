import streamlit as st
import google.generativeai as genai
import os
import re
import json # JSONデータを扱うために必要

# ページ設定
st.set_page_config(page_title="教材理解度テスト自動生成AI", page_icon="📝")

# タイトル
st.title("📝 教材理解度テスト自動生成AI")
st.write("教科書や資料のテキストを貼り付けると、その内容から5択問題を自動で作成します。")

# セッション状態の初期化
if 'quiz_data' not in st.session_state:
    st.session_state.quiz_data = None
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}

# --- サイドバーでAPIキー設定 ---
with st.sidebar:
    st.header("設定")
    
    # 外部公開時にシークレットからキーを読み込む処理
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        api_key_valid = True
    else:
        # ローカル実行時やシークレット未設定時に手動入力を促す
        api_key = st.text_input("Gemini APIキー", type="password")
        if api_key:
            genai.configure(api_key=api_key)
            api_key_valid = True
        else:
            st.warning("APIキーを入力してください。")
            api_key_valid = False

    num_questions = st.slider("作成する問題数", 1, 10, 5)

# --- メインエリア：教材テキスト入力 ---
st.subheader("ステップ1: 教材テキストの貼り付け")
text_input = st.text_area(
    "ここに教科書や資料の本文を貼り付けてください（100字以上推奨）",
    height=300
)

# --- ステップ2: 問題生成ボタン ---
# APIキーとテキストが揃っているか確認
if st.button("問題を生成する") and api_key_valid and text_input:
    if len(text_input) < 100:
        st.error("テキストが短すぎます。100字以上の文章を貼り付けてください。")
    else:
        # AIへの命令（プロンプト）を厳密に定義
        system_prompt = f"""
        あなたはプロの教育コンテンツ作成AIです。
        以下の「入力テキスト」を分析し、その内容だけに基づいた{num_questions}問の5択問題を生成してください。

        【重要ルール】
        1. 問題、正解、不正解の選択肢、そして解説を必ず含むこと。
        2. 正解は必ず一つにすること。
        3. 不正解の選択肢も、知識がないと間違えやすい、関連性の高い内容にすること。
        4. 出力は、以下のJSON形式に**厳密に従って**ください。余計な説明や前置きの文章は一切含めないでください。

        {{
          "questions": [
            {{
              "id": 1,
              "question": "質問文",
              "options": [
                {{"text": "選択肢A", "is_correct": false}},
                {{"text": "選択肢B", "is_correct": true}},
                {{"text": "選択肢C", "is_correct": false}},
                {{"text": "選択肢D", "is_correct": false}}
              ],
              "explanation": "正解の解説文"
            }}
            //... {num_questions}問
          ]
        }}
        """
        
        user_prompt = f"【入力テキスト】\n\n{text_input}"

        try:
            # 安定性と互換性の高い最新モデルを使用
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            with st.spinner(f"📝 {num_questions}問の問題と解答を生成中..."):
                # 修正済み: config -> generation_config に変更し、JSON出力をリクエスト
                response = model.generate_content(
                    [system_prompt, user_prompt],
                    generation_config={"response_mime_type": "application/json"} 
                )

                quiz_data = response.text
                
                # AIが出力したJSON文字列の前後にある不要な文字を削除し、JSONとして読み込む
                match = re.search(r'\{.*\}', quiz_data, re.DOTALL)
                if match:
                    json_string = match.group(0)
                    st.session_state.quiz_data = json.loads(json_string)
                    # ユーザーの解答履歴をリセット
                    st.session_state.user_answers = {} 
                else:
                    st.error("AIからのレスポンスがJSON形式ではありませんでした。テキストの内容を変えて再試行してください。")
                    st.session_state.quiz_data = None
                
        except Exception as e:
            st.error(f"問題生成中にエラーが発生しました: {e}")
            st.session_state.quiz_data = None

# --- ステップ3: 結果の表示 ---
st.subheader("ステップ2: 生成された問題")

if st.session_state.quiz_data:
    questions = st.session_state.quiz_data.get("questions", [])
    
    # 問題を一つずつ表示
    for i, q in enumerate(questions):
        st.markdown(f"**第{i+1}問: {q['question']}**")
        
        # ラジオボタンのキーにはユニークなIDを使用
        user_choice = st.radio(
            "選択してください:",
            options=[opt["text"] for opt in q["options"]],
            key=f"q{i}",
            index=None # 初期値はなし
        )
        
        # ユーザーの解答を保存
        st.session_state.user_answers[f"q{i}"] = user_choice

        # 解答が選択されているかチェックし、結果を表示
        if user_choice:
            is_correct = False
            correct_option = ""
            
            for opt in q["options"]:
                if opt["is_correct"]:
                    correct_option = opt["text"]
                if opt["text"] == user_choice and opt["is_correct"]:
                    is_correct = True
                    break
            
            # 結果表示
            if is_correct:
                st.success("✅ 正解です！")
            else:
                st.error(f"❌ 不正解です。正解は「{correct_option}」でした。")
            
            # 解説表示
            with st.expander("👉 解説を見る"):
                st.write(q["explanation"])
        
        st.markdown("---")
        
    # 全問題の採点結果表示
    if st.button("最終結果を見る"):
        correct_count = 0
        total_questions = len(questions)
        
        for i, q in enumerate(questions):
            user_choice = st.session_state.user_answers.get(f"q{i}")
            if user_choice:
                for opt in q["options"]:
                    if opt["text"] == user_choice and opt["is_correct"]:
                        correct_count += 1
                        break

        if total_questions > 0:
            st.balloons()
            st.subheader("✨ 最終スコア ✨")
            st.metric(
                label="正解率", 
                value=f"{correct_count}/{total_questions}問", 
                delta=f"{(correct_count/total_questions)*100:.1f}%"
            )

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    **開発者メモ:**
    このアプリは、Geminiの**JSON出力機能**を使って、AIに問題という**構造化データ**を作らせています。
    これにより、Python側で解答チェックや表示処理が正確に行えます。
    """
)