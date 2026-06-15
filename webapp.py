"""PM小帮手 Web 界面 — 支持文件上传 & SSE 流式输出"""
import sys, os, json, uuid, re, mimetypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (Flask, render_template, request, jsonify, session,
                   Response, stream_with_context)
from dotenv import load_dotenv
load_dotenv()

from config import Config
from main import agent
from utils import setup_logging

# 初始化日志（与 CLI 入口共用配置；setup_logging 内部有幂等保护）
setup_logging(Config.LOG_FILE)

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB

# ── 启动时清理过期报告（开关：WEB_CLEANUP_ON_START=0 关闭）──
if os.getenv("WEB_CLEANUP_ON_START", "1") == "1":
    try:
        _deleted = Config.cleanup_old_reports()
        if _deleted:
            import logging as _logging
            _logging.getLogger("jira_bot").info("🗑️ 已清理 %d 个超过 %d 天的旧报告",
                                                _deleted, Config.REPORT_MAX_AGE_DAYS)
    except Exception as _e:
        import logging as _logging
        _logging.getLogger("jira_bot").warning("启动清理报告失败（已忽略）: %s", _e)

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
def _sse_iter_events(stream_iter):
    """
    把 LangGraph agent.stream 的输出统一转成 SSE 事件。
    保持向后兼容：assistant 文本仍以 {"text": "..."} 形式发出，前端会拼接。
    新增事件：
      {"type": "thinking"}       — agent 节点产出、还没工具调用
      {"type": "tool_call", "name", "args"} — agent 要调用工具
      {"type": "tool_result", "name", "content", "ok"} — 工具返回
      {"type": "final"}          — 末尾收尾
      {"done": true}             — 终止
    """
    accumulated_text = ""
    last_tool_results = []  # 收集当批工具结果，等下一个 agent 节点一次性 emit

    for chunk in stream_iter:
        if not isinstance(chunk, dict):
            continue
        for node_name, node_output in chunk.items():
            if not isinstance(node_output, dict) or "messages" not in node_output:
                continue
            for msg in node_output["messages"]:
                # 1) ToolMessage：工具返回值
                if msg.__class__.__name__ == "ToolMessage":
                    name = getattr(msg, "name", "") or "tool"
                    content = getattr(msg, "content", "")
                    if isinstance(content, list):
                        # 多模态/分段时只取文本
                        content = "".join(
                            (c.get("text", "") if isinstance(c, dict) else str(c))
                            for c in content
                        )
                    ok = not (isinstance(content, str) and content.startswith("Error"))
                    yield {
                        "type": "tool_result",
                        "name": name,
                        "content": content if isinstance(content, str) else str(content),
                        "ok": ok,
                    }
                    continue

                # 2) AIMessage
                tool_calls = getattr(msg, "tool_calls", None) or []
                text = getattr(msg, "content", "") or ""
                if isinstance(text, list):
                    text = "".join(
                        (c.get("text", "") if isinstance(c, dict) else str(c))
                        for c in text
                    )

                if tool_calls:
                    for tc in tool_calls:
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name", "tool"),
                            "args": tc.get("args", {}),
                        }
                    # 即使带 tool_calls 也可能附带文本思考
                    if text and text.strip():
                        accumulated_text += text
                        yield {"type": "thinking", "content": text}
                elif text and text.strip():
                    # 没有工具调用 → 这是终态回复，分片发出（前端拼接）
                    accumulated_text += text
                    yield {"text": text}

    if accumulated_text:
        yield {"type": "final"}
    yield {"done": True}


def _format_sse(event: dict) -> str:
    """把事件 dict 转成 SSE data 行（json）"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


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
            yield _format_sse({"type": "start", "thread_id": thread_id})
            stream = agent.stream({"messages": [("user", user_message)]}, config=config)
            for event in _sse_iter_events(stream):
                yield _format_sse(event)
        except Exception as e:
            yield _format_sse({"type": "error", "error": str(e)})
            yield _format_sse({"done": True})

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


# ── 文件消息预处理 helper（chat_with_file / chat_with_file_stream 共用）────
def _build_user_message(text: str, file_path: str, file_type: str) -> str:
    """把用户文字 + 附件路径合并成发给 LLM 的 user 消息。

    - 无附件 → 原样返回文字
    - 已知类型（excel/image）→ 按类型给提示前缀或附件标签
    - 未知类型 → 兜底用通用 [附带文件: ...] 标签
    """
    text = (text or "").strip()
    file_path = (file_path or "").strip()
    file_type = (file_type or "").strip()

    if not file_path:
        return text

    if file_type == "excel":
        prefix_hint = "请解析并导入这个 Excel 文件中的任务到 Jira。文件路径"
        tag = f"[附带 Excel 文件: {file_path}]"
    elif file_type == "image":
        prefix_hint = "请识别这张图片中的表格内容并创建对应的 Jira 任务。图片路径"
        tag = f"[附带图片: {file_path}]"
    else:
        # 未知类型：兜底处理，不强加业务暗示
        if text:
            return f"[附带文件: {file_path}]\n{text}"
        return f"请处理附件文件。文件路径: {file_path}"

    if not text:
        return f"{prefix_hint}: {file_path}"
    return f"{tag}\n{text}"


# ── 聊天中附带文件消息 ──────────────────
@app.route("/api/chat_with_file", methods=["POST"])
def chat_with_file():
    """用户发送消息时附带文件路径，AI 自动处理"""
    data = request.get_json()
    user_message = _build_user_message(
        data.get("message"),
        data.get("file_path"),
        data.get("file_type"),
    )

    if not user_message:
        return jsonify({"error": "消息或文件不能为空"}), 400

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


# ── SSE 流式聊天 + 文件 ──────────────────
@app.route("/api/chat_with_file/stream", methods=["POST"])
def chat_with_file_stream():
    data = request.get_json()
    user_message = _build_user_message(
        data.get("message"),
        data.get("file_path"),
        data.get("file_type"),
    )

    if not user_message:
        return jsonify({"error": "消息或文件不能为空"}), 400

    thread_id = get_thread_id()

    def generate():
        config = {"configurable": {"thread_id": thread_id}}
        try:
            yield _format_sse({"type": "start", "thread_id": thread_id})
            stream = agent.stream({"messages": [("user", user_message)]}, config=config)
            for event in _sse_iter_events(stream):
                yield _format_sse(event)
        except Exception as e:
            yield _format_sse({"type": "error", "error": str(e)})
            yield _format_sse({"done": True})

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
    # 生产模式默认走 waitress（多线程、稳定），设置 WEB_DEV=1 才启 Flask 自带服务器（仅开发用）
    if os.getenv("WEB_DEV") == "1":
        print(f"🌐 [DEV] PM小帮手 Web 界面启动（Flask dev server）：http://{host}:{port}")
        app.run(host=host, port=port, debug=True)
    else:
        try:
            from waitress import serve
            threads = int(os.getenv("WEB_THREADS", "4"))
            print(f"🌐 PM小帮手 Web 界面启动（waitress）：http://{host}:{port}（threads={threads}）")
            serve(app, host=host, port=port, threads=threads)
        except ImportError:
            print("⚠️ 未安装 waitress，回退到 Flask dev server（生产请勿使用）")
            app.run(host=host, port=port, debug=False)