"""PM小帮手 Web 界面 — 支持文件上传 & SSE 流式输出"""
import sys, os, json, uuid, re, mimetypes, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import (Flask, render_template, request, jsonify, session,
                   Response, stream_with_context)
from dotenv import load_dotenv
load_dotenv()

from config import Config
from utils import configure_console_encoding, setup_logging

configure_console_encoding()

from agent_factory import build_agent

# 模块级初始化 Agent（与 CLI 共用同一套构建逻辑）
agent, _checkpointer, _jira_client, _llm = build_agent()
from langchain_core.messages import HumanMessage

# 离线模式提示（agent 为 None 时，聊天 API 不可用）
_AGENT_OFFLINE_MSG = "⚠️ Agent 未初始化（LLM/Jira 不可达），请检查网络和 .env 配置后重启。"

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
    """获取当前会话的 thread_id，如果不存在则自动创建。

    thread_id 的生命周期：
    - 首次访问首页 → 自动创建新的 thread_id
    - 每次刷新页面 → 首页重新分配新的 thread_id（新对话）
    - 同一页面内多次聊天 → 共用同一个 thread_id（多轮对话）

    这样设计是为了让「刷新 = 新对话」成为默认行为，
    避免用户刷新后 AI 还带着上个会话的历史上下文。
    """
    if "thread_id" not in session:
        session["thread_id"] = f"web_{uuid.uuid4().hex[:8]}"
    return session["thread_id"]


# ── 首页 ──────────────────────────────────
@app.route("/")
def index():
    # 每次加载首页都分配新的 thread_id，确保刷新页面 = 新对话
    session["thread_id"] = f"web_{uuid.uuid4().hex[:8]}"
    return render_template("chat.html")


# ── 普通聊天 API（非流式）─────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    if agent is None:
        return jsonify({"error": _AGENT_OFFLINE_MSG}), 503
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
async def _sse_iter_events(stream_iter):
    """
    使用 astream_events() 实现真正的 token 级流式输出。
    事件：
      {"text": "..."}           — 逐 token 流式文本
      {"tool_call": "..."}      — AI 正在调用工具（提示前端显示等待状态）
      {"type": "final"}         — 末尾收尾
      {"done": true}            — 终止
    """
    accumulated_text = ""

    async for event in stream_iter:
        kind = event.get("event", "")

        # 工具调用开始 — 仅通知前端（不附带 text，避免被当作回复渲染）
        if kind == "on_tool_start":
            tool_name = event.get("name", "unknown")
            yield {"tool_call": tool_name}
            continue

        # 只取 LLM 逐 token 输出
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                text = chunk.content
                if isinstance(text, list):
                    text = "".join(
                        (c.get("text", "") if isinstance(c, dict) else str(c))
                        for c in text
                    )
                if text:
                    accumulated_text += text
                    yield {"text": text}

    if accumulated_text:
        yield {"type": "final"}
    yield {"done": True}


def _sync_iter(async_gen):
    """在独立线程的事件循环中运行异步迭代器，通过队列流式返回。

    为什么用独立线程而不是直接在当前线程创建 loop：
    - AsyncSqliteSaver / aiosqlite 在 __init__ 时记录事件循环引用
    - Flask/Waitress 每个请求可能在不同线程
    - 如果 checkpointer 的 loop 与迭代 loop 不同，aiosqlite 的 run_in_executor
      返回的 Future 会绑定到错误的 loop，导致 hang
    - 独立线程 + 独立 loop 确保 aiosqlite 操作在正确的 loop 上执行
    """
    import asyncio
    import threading
    from queue import Queue

    queue: "Queue" = Queue()
    _error: list = [None]  # 跨线程传递异常

    async def _collect():
        try:
            async for item in async_gen:
                queue.put(("value", item))
            queue.put(("done", None))
        except BaseException as e:
            _error[0] = e
            queue.put(("error", e))

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_collect())
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    while True:
        kind, payload = queue.get()
        if kind == "done":
            break
        if kind == "error":
            raise RuntimeError(f"异步流内部错误: {payload}") from payload
        yield payload


def _format_sse(event: dict) -> str:
    """把事件 dict 转成 SSE data 行（json）"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    if agent is None:
        return jsonify({"error": _AGENT_OFFLINE_MSG}), 503
    data = request.get_json()
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    thread_id = get_thread_id()

    def generate():
        config = {"configurable": {"thread_id": thread_id}}
        try:
            yield _format_sse({"type": "start", "thread_id": thread_id})
            events = agent.astream_events(
                {"messages": [("user", user_message)]},
                config=config,
                version="v2"
            )
            for sse_event in _sync_iter(_sse_iter_events(events)):
                # 客户端断开时立即停止生成，避免资源浪费
                # Flask dev server 的 request 没有 is_disconnected，用 hasattr 保护
                if getattr(request, 'is_disconnected', lambda: False)():
                    break
                yield _format_sse(sse_event)
        except GeneratorExit:
            # 客户端断开时 Flask 会关闭生成器
            pass
        except Exception as e:
            yield _format_sse({"type": "error", "error": str(e)})
            yield _format_sse({"done": True})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        }
    )


@app.route("/api/chat_with_file/stream", methods=["POST"])
def chat_with_file_stream():
    if agent is None:
        return jsonify({"error": _AGENT_OFFLINE_MSG}), 503
    data = request.get_json()
    user_msg = _build_user_message(
        data.get("message"),
        data.get("file_path"),
        data.get("file_type"),
    )

    if not user_msg or not user_msg.get("content"):
        return jsonify({"error": "消息或文件不能为空"}), 400

    thread_id = get_thread_id()

    def generate():
        agent_input, config = _build_input(user_msg, thread_id)
        try:
            yield _format_sse({"type": "start", "thread_id": thread_id})
            events = agent.astream_events(
                agent_input,
                config=config,
                version="v2"
            )
            for sse_event in _sync_iter(_sse_iter_events(events)):
                if getattr(request, 'is_disconnected', lambda: False)():
                    break
                yield _format_sse(sse_event)
        except GeneratorExit:
            pass
        except Exception as e:
            yield _format_sse({"type": "error", "error": str(e)})
            yield _format_sse({"done": True})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream; charset=utf-8",
        }
    )


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
def _build_user_message(text: str, file_path: str, file_type: str) -> dict:
    """把用户文字 + 附件路径合并成发给 LLM 的消息。

    返回 {"is_multimodal": bool, "content": str|list}
    - 非图片附件 / 纯文本: is_multimodal=False, content 为纯文本字符串
    - 图片附件: is_multimodal=True, content 为多模态内容列表（含 base64 图片）
    """
    text = (text or "").strip()
    file_path = (file_path or "").strip()
    file_type = (file_type or "").strip()

    if not file_path:
        return {"is_multimodal": False, "content": text}

    if file_type == "image":
        # 读取图片并 base64 编码，构造多模态消息
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".bmp": "image/bmp",
        }
        mime_type = mime_map.get(ext, "image/png")

        with open(file_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        content = []
        if text:
            content.append({"type": "text", "text": text})
        else:
            content.append({"type": "text", "text": "请识别这张图片中的内容，并执行相应的操作。"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{img_b64}"},
        })
        return {"is_multimodal": True, "content": content}

    if file_type == "excel":
        prefix_hint = "请解析并导入这个 Excel 文件中的任务到 Jira。文件路径"
        tag = f"[附带 Excel 文件: {file_path}]"
        if not text:
            return {"is_multimodal": False, "content": f"{prefix_hint}: {file_path}"}
        return {"is_multimodal": False, "content": f"{tag}\n{text}"}

    # 未知类型：兜底处理
    if text:
        return {"is_multimodal": False, "content": f"[附带文件: {file_path}]\n{text}"}
    return {"is_multimodal": False, "content": f"请处理附件文件。文件路径: {file_path}"}


def _build_input(msg: dict, thread_id: str) -> tuple:
    """根据消息类型构建传给 agent 的 input。

    返回 (input_dict, config_dict)
    - 多模态图片: 用 HumanMessage(content=list)
    - 普通文本: 用 ("user", text) 元组
    """
    config = {"configurable": {"thread_id": thread_id}}
    if msg["is_multimodal"]:
        return ({"messages": [HumanMessage(content=msg["content"])]}, config)
    else:
        return ({"messages": [("user", msg["content"])]}, config)


# ── 聊天中附带文件消息 ──────────────────
@app.route("/api/chat_with_file", methods=["POST"])
def chat_with_file():
    if agent is None:
        return jsonify({"error": _AGENT_OFFLINE_MSG}), 503
    """用户发送消息时附带文件路径，AI 自动处理"""
    data = request.get_json()
    user_msg = _build_user_message(
        data.get("message"),
        data.get("file_path"),
        data.get("file_type"),
    )

    if not user_msg or not user_msg.get("content"):
        return jsonify({"error": "消息或文件不能为空"}), 400

    thread_id = get_thread_id()
    agent_input, config = _build_input(user_msg, thread_id)

    try:
        response = agent.invoke(agent_input, config=config)
        reply = ""
        if response and "messages" in response:
            reply = response["messages"][-1].content or ""
        return jsonify({"reply": reply, "thread_id": thread_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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