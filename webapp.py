"""PM小帮手 Web 界面 — 支持文件上传 & SSE 流式输出"""
import sys, os, json, uuid, re, mimetypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (Flask, render_template, request, jsonify, session,
                   Response, stream_with_context)
from dotenv import load_dotenv
load_dotenv()

from config import Config
from main import agent

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

HTML_REPORT_URL_PREFIX = "/report"
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".bmp"}


def get_thread_id():
    if "thread_id" not in session:
        session["thread_id"] = f"web_{uuid.uuid4().hex[:8]}"
    return session["thread_id"]


# ── 首页 ──────────────────────────────────
@app.route("/")
def index():
    return render_template("chat.html")


# ── 普通聊天 API（非流式）─────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
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
        return jsonify({"reply": reply, "thread_id": thread_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── SSE 流式聊天 API ──────────────────────
@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    thread_id = get_thread_id()

    def generate():
        config = {"configurable": {"thread_id": thread_id}}
        try:
            # 使用 stream 模式
            for chunk in agent.stream(
                {"messages": [("user", user_message)]},
                config=config
            ):
                # chunk 是 dict，可能包含 agent 或 tools 的增量
                if isinstance(chunk, dict):
                    for node_name, node_output in chunk.items():
                        if isinstance(node_output, dict) and "messages" in node_output:
                            msgs = node_output["messages"]
                            if msgs:
                                last = msgs[-1]
                                if hasattr(last, "content") and last.content:
                                    yield f"data: {json.dumps({'text': last.content})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ── 文件上传 API ──────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_file():
    """上传 Excel / 图片文件，返回文件路径"""
    if "file" not in request.files:
        return jsonify({"error": "未选择文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "文件名为空"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"不支持的文件类型: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    # 保存文件
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(Config.UPLOAD_DIR, safe_name)
    file.save(save_path)

    file_type = "excel" if ext in (".xlsx", ".xls") else "image"
    return jsonify({
        "file_path": save_path,
        "file_name": file.filename,
        "file_type": file_type,
        "message": f"文件已上传: {file.filename}"
    })


# ── 聊天中附带文件消息 ──────────────────
@app.route("/api/chat_with_file", methods=["POST"])
def chat_with_file():
    """用户发送消息时附带文件路径，AI 自动处理"""
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    file_path = (data.get("file_path") or "").strip()
    file_type = (data.get("file_type") or "").strip()

    if not user_message and not file_path:
        return jsonify({"error": "消息或文件不能为空"}), 400

    thread_id = get_thread_id()
    config = {"configurable": {"thread_id": thread_id}}

    # 在用户消息前插入系统指令
    system_note = ""
    if file_path and file_type == "excel":
        if not user_message:
            user_message = f"请解析并导入这个 Excel 文件中的任务到 Jira。文件路径: {file_path}"
        else:
            user_message = f"[附带 Excel 文件: {file_path}]\n{user_message}"
    elif file_path and file_type == "image":
        if not user_message:
            user_message = f"请识别这张图片中的表格内容并创建对应的 Jira 任务。图片路径: {file_path}"
        else:
            user_message = f"[附带图片: {file_path}]\n{user_message}"

    try:
        response = agent.invoke(
            {"messages": [("user", user_message)]},
            config=config
        )
        reply = ""
        if response and "messages" in response:
            reply = response["messages"][-1].content or ""
        return jsonify({"reply": reply, "thread_id": thread_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── SSE 流式聊天 + 文件 ──────────────────
@app.route("/api/chat_with_file/stream", methods=["POST"])
def chat_with_file_stream():
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    file_path = (data.get("file_path") or "").strip()
    file_type = (data.get("file_type") or "").strip()

    if not user_message and not file_path:
        return jsonify({"error": "消息或文件不能为空"}), 400

    thread_id = get_thread_id()

    if file_path and file_type == "excel":
        if not user_message:
            user_message = f"请解析并导入这个 Excel 文件中的任务到 Jira。文件路径: {file_path}"
        else:
            user_message = f"[附带 Excel 文件: {file_path}]\n{user_message}"
    elif file_path and file_type == "image":
        if not user_message:
            user_message = f"请识别这张图片中的表格内容并创建对应的 Jira 任务。图片路径: {file_path}"
        else:
            user_message = f"[附带图片: {file_path}]\n{user_message}"

    def generate():
        config = {"configurable": {"thread_id": thread_id}}
        try:
            for chunk in agent.stream(
                {"messages": [("user", user_message)]},
                config=config
            ):
                if isinstance(chunk, dict):
                    for node_name, node_output in chunk.items():
                        if isinstance(node_output, dict) and "messages" in node_output:
                            msgs = node_output["messages"]
                            if msgs:
                                last = msgs[-1]
                                if hasattr(last, "content") and last.content:
                                    yield f"data: {json.dumps({'text': last.content})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ── 重置会话 ──────────────────────────
@app.route("/api/reset", methods=["POST"])
def reset_conversation():
    session.pop("thread_id", None)
    return jsonify({"status": "ok"})


# ── 报告文件代理 ──────────────────────────
@app.route(HTML_REPORT_URL_PREFIX + "/<path:filename>")
def serve_report(filename):
    from flask import send_from_directory
    return send_from_directory(Config.REPORTS_DIR, filename)


if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "5000"))
    host = os.getenv("WEB_HOST", "127.0.0.1")
    print(f"🌐 PM小帮手 Web 界面启动：http://{host}:{port}")
    app.run(host=host, port=port, debug=True)