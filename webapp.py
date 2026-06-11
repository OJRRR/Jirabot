"""Jira AI Agent Web 界面（Flask）"""
import sys, os, json, uuid, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
load_dotenv()

from config import Config
from main import agent

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

HTML_REPORT_URL_PREFIX = "/report"


def get_thread_id():
    """获取当前会话的 thread_id"""
    if "thread_id" not in session:
        session["thread_id"] = f"web_{uuid.uuid4().hex[:8]}"
    return session["thread_id"]


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    """处理用户消息并返回 AI 回复"""
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    thread_id = get_thread_id()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        response = agent.invoke(
            {"messages": [("user", user_message)]},
            config=config
        )
        reply = ""
        if response and "messages" in response:
            reply = response["messages"][-1].content or ""

        return jsonify({
            "reply": reply,
            "thread_id": thread_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def reset_conversation():
    """重置会话"""
    session.pop("thread_id", None)
    return jsonify({"status": "ok"})


@app.route(HTML_REPORT_URL_PREFIX + "/<path:filename>")
def serve_report(filename):
    """提供生成的 HTML 报告"""
    from flask import send_from_directory
    return send_from_directory(Config.REPORTS_DIR, filename)


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "5000"))
    host = os.getenv("WEB_HOST", "127.0.0.1")
    print(f"🌐 Jira AI Agent Web 界面启动：http://{host}:{port}")
    print(f"   Python 代码中可直接打开 http://127.0.0.1:{port}")
    app.run(host=host, port=port, debug=True)