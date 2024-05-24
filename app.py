import os
import openai
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *

import traceback

# Flask應用初始化
app = Flask(__name__)
static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

# Line Bot API 初始化
line_bot_api = LineBotApi(os.getenv('CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('CHANNEL_SECRET'))

# OpenAI API Key初始化
openai.api_key = os.getenv('OPENAI_API_KEY')

def get_news():
    url = 'https://tw.stock.yahoo.com/tw-market'  # Yahoo奇摩股市新聞頁面
    try:
        response = requests.get(url)
        response.raise_for_status()  # 對於錯誤響應拋出HTTPError
    except requests.RequestException as e:
        print(f"Error fetching the news: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 根據網站結構調整抓取新聞的方法
    articles = soup.find_all('li', class_='js-stream-content')
    news_list = []
    
    for article in articles:
        title = article.find('h3').text if article.find('h3') else 'No title'
        content = article.find('p').text if article.find('p') else 'No content'
        news_list.append({'title': title, 'content': content})
    
    return news_list

def analyze_news(news_list):
    analyzed_news = []
    for news in news_list:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": f"整理完並分析以下股市新聞，重點列出你的看法，並找出文中提到的公司及其在台灣的小型供應商名稱。最後的順序是：你的看法，提及的公司，其在台灣的小型供應商名稱：\n\n{news['content']}\n\n結果："},
                ],
                max_tokens=2000
            )
            result = response['choices'][0]['message']['content'].strip()
            analyzed_news.append({'title': news['title'], 'content': news['content'], 'analysis': result})
        except openai.error.OpenAIError as e:
            print(f"Error analyzing the news: {e}")
            analyzed_news.append({'title': news['title'], 'content': news['content'], 'analysis': 'Error analyzing this news.'})
    
    return analyzed_news

def GPT_response(text):
    try:
        response = openai.Completion.create(model="gpt-3.5-turbo-instruct", prompt=text, temperature=0.5, max_tokens=500)
        print(response)
        answer = response['choices'][0]['text'].replace('。','')
        return answer
    except openai.error.OpenAIError as e:
        print(f"Error with OpenAI API: {e}")
        return "Error with OpenAI API."

# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text
    try:
        if msg == "最新新聞":
            news_list = get_news()
            analyzed_news = analyze_news(news_list)
            response_text = "\n\n".join([f"標題: {news['title']}\n分析: {news['analysis']}" for news in analyzed_news])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(response_text))
        else:
            GPT_answer = GPT_response(msg)
            print(GPT_answer)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(GPT_answer))
    except:
        print(traceback.format_exc())
        line_bot_api.reply_message(event.reply_token, TextSendMessage('你所使用的OPENAI API key額度可能已經超過，請於後台Log內確認錯誤訊息'))

@handler.add(PostbackEvent)
def handle_postback(event):
    print(event.postback.data)

@handler.add(MemberJoinedEvent)
def welcome(event):
    uid = event.joined.members[0].user_id
    gid = event.source.group_id
    profile = line_bot_api.get_group_member_profile(gid, uid)
    name = profile.display_name
    message = TextSendMessage(text=f'{name}歡迎加入')
    line_bot_api.reply_message(event.reply_token, message)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
