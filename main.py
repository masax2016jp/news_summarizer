import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
import feedparser
from google import genai

# 環境変数の読み込み
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")       # 送信元（Gmail）
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")   # Gmailのアプリパスワード
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")   # 送信先（ご自身のメールアドレスなど）

# 取得するRSSフィードのリスト（論文と一般ニュース）
FEEDS = {
    "最新論文 (arXiv)": "http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL&sortBy=lastUpdatedDate&sortOrder=descending&max_results=5",
    "TechCrunch (AIニュース)": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "VentureBeat (AIニュース)": "https://feeds.feedburner.com/venturebeat/SZYF"
}

def fetch_recent_articles(feeds_dict, max_hours=24):
    """過去24時間以内の記事をフィードから収集する"""
    now = datetime.now(timezone.utc)
    recent_articles = []
    
    for category, url in feeds_dict.items():
        print(f"[{category}] のフィードを取得中...")
        parsed_feed = feedparser.parse(url)
        
        for entry in parsed_feed.entries:
            # 記事の公開日時を取得・パース
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published_time = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            else:
                continue
                
            # 過去24時間（デフォルト）以内の記事か判定
            if now - published_time <= timedelta(hours=max_hours):
                recent_articles.append({
                    "category": category,
                    "title": entry.title,
                    "link": entry.link,
                    "summary": getattr(entry, "summary", "")
                })
                
    return recent_articles

def summarize_with_gemini(articles):
    """取得した記事リストをGeminiで要約・日本語に翻訳・整理する"""
    if not articles:
        return "新しいニュースはありませんでした。"

    # Geminiに渡すテキストデータを組み立てる
    prompt = "以下の直近のAI関連ニュースや論文の最新情報を、日本語で分かりやすく要約・整理してメールマガジン形式で作成してください。\n\n"
    prompt += "【条件】\n"
    prompt += "1. 一般的なニュースと論文（arXiv）は見出しを分けてセクションにすること\n"
    prompt += "2. 各項目のタイトルは日本語に翻訳すること\n"
    prompt += "3. 各ニュース/論文について、2〜3行程度で「何が面白いか・重要か」を解説すること\n"
    prompt += "4. 専門用語が難しすぎる場合は軽く補足すること\n"
    prompt += "5. トーンは「プロフェッショナルのリサーチャー」が同僚に共有するような少しカジュアルかつ知的なトーンにすること\n"
    prompt += "6. 【重要】各記事のリンク（URL）は、以下の【生データ】にある 'Link:' の文字列を一文字も変更せずそのまま記載すること。AIによるURLの編集や捏造は厳禁です。\n"
    prompt += "7. 【重要】URLは前後にカッコなどをつけず、必ず改行して独立した行に書いてください（Markdownの [テキスト](URL) 形式も使用不可）。\n\n"
    prompt += "【生データ（タイトルと概要、URL）】\n"
    
    for i, a in enumerate(articles):
        # 概要が長すぎる場合があるため、最初の500文字で制限する
        summary_text = a['summary'][:500] + ("..." if len(a['summary']) > 500 else "")
        prompt += f"--- 記事 {i+1} ({a['category']}) ---\n"
        prompt += f"Title: {a['title']}\n"
        prompt += f"Link: {a['link']}\n"
        prompt += f"Summary/Abstract: {summary_text}\n\n"

    print("Gemini APIで要約を生成中...")
    try:
        # 新しい google-genai SDK への書き換え
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash', # 高速・低コストなモデル（通常枠で十分無料範囲内）
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Gemini API エラー: {e}")
        return "記事は取得できましたが、要約中にエラーが発生しました。\n\n" + str(e)

def send_email(subject, body):
    """要約結果を指定のメールアドレスに送信する"""
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL

    # SSLを有効にしてSMTP経由で送信 (Gmailの場合)
    context = ssl.create_default_context()
    print("メールを送信中...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, EMAIL_PASSWORD)
            server.send_message(msg)
        print("メールの送信が完了しました！")
    except Exception as e:
        print(f"メール送信エラー: {e}")

def main():
    if not all([GEMINI_API_KEY, SENDER_EMAIL, EMAIL_PASSWORD, RECEIVER_EMAIL]):
        print("必要な環境変数が設定されていません。終了します。")
        return

    articles = fetch_recent_articles(FEEDS, max_hours=24)
    print(f"{len(articles)}件の最新記事が見つかりました。")
    
    if len(articles) == 0:
        print("送信する内容がないため、処理を終了します。")
        return

    final_summary = summarize_with_gemini(articles)
    
    # ---- ▼ ここから追加・変更：冒頭と末尾の固定メッセージ ----
    header = "おはようございます！本日のAI関連ニュースと論文のまとめをお届けします。\n\n"
    footer = "\n\n━━━━━━━━━━━━━━━━━━━━\n"
    footer += "※このメールはGitHub Actions + Gemini API によって自動配信されています。\n"
    
    mail_body = header + final_summary + footer
    # ---- ▲ ここまで ----

    # メールのタイトルには今日の日付を入れる
    today_str = datetime.now().strftime("%Y年%m月%d日")
    subject = f"【日刊 AI論文＆ニュース】自動要約ダイジェスト ({today_str})"
    
    # 送信する内容を final_summary から mail_body に変更
    send_email(subject, mail_body)

if __name__ == "__main__":
    main()
