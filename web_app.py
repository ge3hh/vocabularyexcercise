import html
import io
import os
import secrets
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from vocabulary_pool import (
    DEFAULT_LIBRARY_NAME,
    LIBRARY_TABLES,
    clear_up_db,
    ensure_all_libraries,
    export_vocabulary_db,
    get_library_word_count,
    get_recent_first_test_records,
    get_statistics,
    get_words_for_test,
    get_wrong_words,
    import_new_words,
    record_practice_result,
)


BASE_DIR = Path(__file__).resolve().parent
BUILTIN_LIBRARY_FILES = {
    "高中词库": BASE_DIR / "learning.csv",
    "大学四级词库": BASE_DIR / "cet4.csv",
    "大学六级词库": BASE_DIR / "cet6.csv",
}

HOST = "0.0.0.0"
PORT = 5000
SESSIONS = {}


def escape(value):
    return html.escape(str(value), quote=True)


def parse_multipart(content_type, body):
    boundary_marker = "boundary="
    if boundary_marker not in content_type:
        return {}

    boundary = content_type.split(boundary_marker, 1)[1].strip().strip('"')
    delimiter = f"--{boundary}".encode()
    parsed = {}

    for chunk in body.split(delimiter):
        chunk = chunk.strip()
        if not chunk or chunk == b"--":
            continue

        if b"\r\n\r\n" not in chunk:
            continue

        header_bytes, content = chunk.split(b"\r\n\r\n", 1)
        content = content.rstrip(b"\r\n")
        headers = header_bytes.decode("utf-8", errors="ignore").split("\r\n")
        disposition_line = next((line for line in headers if line.lower().startswith("content-disposition:")), "")
        if not disposition_line:
            continue

        parts = disposition_line.split(";")
        params = {}
        for item in parts[1:]:
            if "=" in item:
                key, value = item.strip().split("=", 1)
                params[key.strip()] = value.strip().strip('"')

        field_name = params.get("name")
        if not field_name:
            continue

        parsed[field_name] = {
            "filename": params.get("filename", ""),
            "content": content,
        }

    return parsed


def get_library_name(session_state):
    library_name = session_state.get("library_name", DEFAULT_LIBRARY_NAME)
    if library_name not in LIBRARY_TABLES:
        library_name = DEFAULT_LIBRARY_NAME
        session_state["library_name"] = library_name
    return library_name


def get_table_name(session_state):
    return LIBRARY_TABLES[get_library_name(session_state)]


def reset_quiz_state(session_state):
    session_state["quiz_words"] = []
    session_state["quiz_index"] = 0
    session_state["learned_words"] = []
    session_state["unknown_words"] = []
    session_state["pending_result"] = None


def get_session_state(handler):
    session_cookie = cookies.SimpleCookie(handler.headers.get("Cookie"))
    session_id = None
    if "vocabulary_session" in session_cookie:
        session_id = session_cookie["vocabulary_session"].value

    if not session_id or session_id not in SESSIONS:
        session_id = secrets.token_hex(16)
        SESSIONS[session_id] = {"library_name": DEFAULT_LIBRARY_NAME, "flashes": []}
        reset_quiz_state(SESSIONS[session_id])
        handler.session_cookie_header = f"vocabulary_session={session_id}; Path=/; HttpOnly; SameSite=Lax"

    return SESSIONS[session_id]


def add_flash(session_state, category, message):
    session_state.setdefault("flashes", []).append((category, message))


def pop_flashes(session_state):
    flashes = session_state.get("flashes", [])
    session_state["flashes"] = []
    return flashes


def render_page(session_state):
    ensure_all_libraries()
    smooth_scroll_target = session_state.pop("smooth_scroll_target", "")
    library_name = get_library_name(session_state)
    table_name = get_table_name(session_state)
    stats = get_statistics(table_name)
    wrong_words = get_wrong_words(table_name, limit=50)
    recent_first_tests = get_recent_first_test_records(table_name, limit=50)
    quiz_words = session_state.get("quiz_words", [])
    quiz_index = session_state.get("quiz_index", 0)
    current_word = quiz_words[quiz_index] if 0 <= quiz_index < len(quiz_words) else None
    learned_words = session_state.get("learned_words", [])
    unknown_words = session_state.get("unknown_words", [])
    pending_result = session_state.get("pending_result")
    total_words = max(stats["total_words"], 1)

    flash_html = "".join(
        f'<div class="flash {"error" if category == "error" else ""}">{escape(message)}</div>'
        for category, message in pop_flashes(session_state)
    )

    library_options = "".join(
        f'<option value="{escape(name)}" {"selected" if name == library_name else ""}>{escape(name)}</option>'
        for name in LIBRARY_TABLES
    )

    is_quiz_active = bool(current_word or pending_result)
    quiz_state_label = "查看结果" if pending_result else ("正在答题" if current_word else "等待开始")
    quiz_shell_class = "quiz-shell active" if is_quiz_active else "quiz-shell"

    if pending_result:
        action_text = "认识" if pending_result["is_known"] else "不认识"
        next_label = "完成本轮" if pending_result["is_finished"] else "下一个单词"
        quiz_html = f"""
        <div class="quiz-card result-card">
            <p class="muted">已选择：{action_text}</p>
            <div class="word">{escape(pending_result['english'])}</div>
            <p class="muted">词义：{escape(pending_result['chinese'] or '未填写释义')}</p>
            <p class="muted">下次复习：{escape(pending_result['next_review_date'] or '待安排')}</p>
            <form method="post" action="/quiz/next" style="margin-top: 18px;">
                <button type="submit" class="quiz-primary-button">{next_label}</button>
            </form>
        </div>
        """
    elif current_word:
        quiz_html = f"""
        <div class="quiz-card">
            <p class="muted">第 {quiz_index + 1} / {len(quiz_words)} 个</p>
            <div class="word">{escape(current_word['english'])}</div>
            <p class="muted">先判断是否认识，再查看词义。</p>
            <div class="answer-actions">
                <form method="post" action="/quiz/answer" class="answer-form">
                    <input type="hidden" name="answer" value="known">
                    <button type="submit" class="answer-option answer-known">认识</button>
                </form>
                <form method="post" action="/quiz/answer" class="answer-form">
                    <input type="hidden" name="answer" value="unknown">
                    <button type="submit" class="answer-option answer-unknown">不认识</button>
                </form>
            </div>
        </div>
        """
    else:
        quiz_html = """
        <div class="quiz-card">
            <div class="word" style="font-size: 28px;">准备开始新一轮测试</div>
            <p class="muted">先导入词库，再设置测试数量并开始测试。</p>
        </div>
        """

    learned_count = len(learned_words)
    unknown_count = len(unknown_words)
    learned_items = "".join(f"<li>{escape(word)}</li>" for word in reversed(learned_words)) or '<li class="muted">当前还没有开始测试。</li>'
    unknown_items = "".join(f"<li>{escape(item)}</li>" for item in reversed(unknown_words)) or '<li class="muted">当前没有本轮错题。</li>'
    wrong_items = "".join(
        f"<li><strong>{escape(item['english'])}</strong><div class=\"muted\">{escape(item['chinese'] or '未填写释义')}</div><div class=\"muted\">错误次数：{item['wrong_count']} | 最近错误：{escape(item['last_wrong_date'])}</div></li>"
        for item in wrong_words
    ) or '<li class="muted">当前词库还没有错题记录。</li>'
    first_test_items = "".join(
        f"<li><strong>{escape(item['english'])}</strong><div class=\"muted\">{escape(item['chinese'] or '未填写释义')}</div><div class=\"muted\">首次测试：{escape(item['first_test_date'])}</div></li>"
        for item in recent_first_tests
    ) or '<li class="muted">当前词库还没有首次测试记录。</li>'

    stat_cards = [
        ("总词数", stats["total_words"]),
        ("已测试词数", stats["tested_words"]),
        ("待复习词数", stats["due_words"]),
        ("错题本条目", stats["wrong_notebook_count"]),
        ("学习中", stats["learning_words"]),
        ("已掌握", stats["mastered_words"]),
        ("累计练习", stats["total_practice"]),
        ("累计答错", stats["total_wrong"]),
    ]
    stat_html = "".join(
        f'<div class="stat-card"><span class="muted">{escape(label)}</span><strong>{escape(value)}</strong></div>'
        for label, value in stat_cards
    )

    smooth_scroll_script = ""
    if smooth_scroll_target:
        target = escape(smooth_scroll_target)
        smooth_scroll_script = f"""
    <script>
        window.addEventListener("load", function () {{
            var target = document.getElementById("{target}");
            if (!target) {{
                return;
            }}
            requestAnimationFrame(function () {{
                target.scrollIntoView({{ behavior: "smooth", block: "start" }});
            }});
        }});
    </script>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Vocabulary Exercise Web</title>
    <style>
        :root {{
            --bg: #f4efe6; --panel: #fffdf8; --line: #dccfb8; --text: #27211a; --muted: #6f6557;
            --accent: #0f766e; --accent-strong: #115e59; --warn: #b45309; --danger: #b91c1c;
            --known: #15803d; --known-strong: #166534; --unknown: #b91c1c; --unknown-strong: #991b1b;
            --success-bg: #ecfdf5; --error-bg: #fef2f2;
        }}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: var(--text); background: radial-gradient(circle at top right, rgba(15, 118, 110, 0.12), transparent 28%), linear-gradient(180deg, #f8f3eb 0%, var(--bg) 100%); }}
        .page {{ width: min(1180px, calc(100vw - 32px)); margin: 24px auto 40px; }}
        .hero {{ padding: 28px; border-radius: 22px; background: linear-gradient(135deg, #fffaf0 0%, #fff 55%, #eefcf9 100%); border: 1px solid var(--line); box-shadow: 0 12px 40px rgba(39, 33, 26, 0.08); }}
        h1, h2, h3, p {{ margin-top: 0; }}
        .hero h1 {{ font-size: clamp(30px, 4vw, 46px); margin-bottom: 8px; }}
        .hero p {{ color: var(--muted); margin-bottom: 0; }}
        .flash-list {{ margin: 16px 0; display: grid; gap: 10px; }}
        .flash {{ padding: 12px 16px; border-radius: 14px; border: 1px solid var(--line); background: var(--success-bg); }}
        .flash.error {{ background: var(--error-bg); border-color: #fecaca; }}
        .grid {{ display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 20px; margin-top: 20px; }}
        .panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 20px; padding: 20px; box-shadow: 0 10px 30px rgba(39, 33, 26, 0.06); }}
        .panel h2 {{ font-size: 22px; margin-bottom: 16px; }}
        .toolbar, .actions, .stats-grid {{ display: grid; gap: 12px; }}
        .toolbar {{ grid-template-columns: 1.2fr 1fr auto auto; align-items: end; }}
        .test-toolbar {{ display: grid; grid-template-columns: minmax(180px, 1.35fr) minmax(120px, 0.8fr) auto; gap: 10px; align-items: end; }}
        .test-action-row {{ display: grid; grid-template-columns: 2fr 1fr; gap: 10px; margin-top: 10px; }}
        .actions {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
        .stats-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        .stat-card {{ padding: 14px; border: 1px solid var(--line); border-radius: 16px; background: #fff; }}
        .stat-card strong {{ display: block; font-size: 24px; margin-top: 6px; }}
        label {{ display: block; font-size: 14px; color: var(--muted); margin-bottom: 6px; }}
        input, select, button {{ width: 100%; border-radius: 12px; border: 1px solid var(--line); padding: 12px 14px; font: inherit; }}
        button {{ cursor: pointer; background: var(--accent); color: #fff; border-color: var(--accent); transition: transform 0.15s ease, background 0.15s ease; }}
        button:hover {{ transform: translateY(-1px); background: var(--accent-strong); }}
        .secondary {{ background: #fff; color: var(--text); }}
        .warn {{ background: #fff7ed; color: var(--warn); border-color: #fdba74; }}
        .danger {{ background: #fef2f2; color: var(--danger); border-color: #fca5a5; }}
        #quiz-section {{ margin-top: 18px; scroll-margin-top: 18px; }}
        .quiz-shell {{ padding: 16px; border: 1px solid #e7dbc6; border-radius: 22px; background: linear-gradient(180deg, #fffaf2 0%, #fffefb 100%); box-shadow: 0 10px 26px rgba(39, 33, 26, 0.05); }}
        .quiz-shell.active {{ border-color: rgba(15, 118, 110, 0.35); background: linear-gradient(180deg, rgba(15, 118, 110, 0.08) 0%, #fffef9 22%, #ffffff 100%); box-shadow: 0 18px 40px rgba(15, 118, 110, 0.12); }}
        .quiz-shell-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }}
        .quiz-badge {{ display: inline-flex; align-items: center; padding: 6px 12px; border-radius: 999px; background: rgba(15, 118, 110, 0.12); color: var(--accent-strong); font-size: 13px; font-weight: 700; }}
        .quiz-card {{ padding: 36px 24px 40px; border: 1px dashed var(--line); border-radius: 18px; background: linear-gradient(180deg, #fffcf5 0%, #ffffff 100%); margin-top: 0; text-align: center; }}
        .quiz-shell.active .quiz-card {{ min-height: 380px; display: flex; flex-direction: column; justify-content: center; }}
        .result-card {{ border-style: solid; border-color: rgba(15, 118, 110, 0.2); }}
        .group-card {{ border: 1px solid var(--line); border-radius: 16px; padding: 16px; background: #fff; margin-top: 16px; }}
        .group-card h3 {{ margin-bottom: 12px; }}
        .compact-controls label {{ font-size: 12px; }}
        .compact-controls input, .compact-controls select {{ font-size: 14px; padding: 10px 12px; }}
        .compact-controls button {{ font-size: 14px; padding: 10px 12px; }}
        .compact-controls h3 {{ font-size: 18px; margin-bottom: 10px; }}
        .toolbar-strip {{ padding: 12px 14px; }}
        .toolbar-strip h3 {{ margin: 0 0 8px; font-size: 16px; }}
        .tool-field {{ min-width: 0; }}
        .tool-field label {{ margin-bottom: 4px; }}
        .tool-button {{ min-width: 112px; white-space: nowrap; }}
        details.collapsible {{ padding: 0; overflow: hidden; }}
        details.collapsible summary {{ list-style: none; cursor: pointer; padding: 14px 16px; font-size: 16px; font-weight: 600; }}
        details.collapsible summary::-webkit-details-marker {{ display: none; }}
        details.collapsible summary::after {{ content: '展开'; float: right; color: var(--muted); font-size: 13px; font-weight: 500; }}
        details.collapsible[open] summary {{ border-bottom: 1px solid #efe7da; }}
        details.collapsible[open] summary::after {{ content: '收起'; }}
        .collapsible-body {{ padding: 14px 16px 16px; }}
        .word {{ font-size: clamp(42px, 6vw, 68px); font-weight: 700; letter-spacing: 0.03em; margin: 28px 0 30px; line-height: 1.08; }}
        .muted {{ color: var(--muted); }}
        .answer-actions {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 22px; }}
        .answer-form {{ margin: 0; }}
        .answer-actions button, .quiz-primary-button {{ min-height: 64px; font-size: 18px; font-weight: 700; }}
        .answer-option {{ border-width: 2px; box-shadow: 0 12px 24px rgba(39, 33, 26, 0.12); }}
        .answer-known {{ background: linear-gradient(180deg, #22c55e 0%, var(--known) 100%); border-color: var(--known-strong); color: #f7fff8; }}
        .answer-known:hover {{ background: linear-gradient(180deg, #16a34a 0%, var(--known-strong) 100%); }}
        .answer-unknown {{ background: linear-gradient(180deg, #ef4444 0%, var(--unknown) 100%); border-color: var(--unknown-strong); color: #fff7f7; }}
        .answer-unknown:hover {{ background: linear-gradient(180deg, #dc2626 0%, var(--unknown-strong) 100%); }}
        .lists {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 18px; }}
        .list-card {{ border: 1px solid var(--line); border-radius: 16px; padding: 16px; background: #fff; }}
        ul.clean {{ list-style: none; padding-left: 0; margin: 0; display: grid; gap: 10px; }}
        ul.clean li {{ padding-bottom: 10px; border-bottom: 1px solid #efe7da; }}
        ul.clean li:last-child {{ border-bottom: 0; padding-bottom: 0; }}
        .scroll-list {{ max-height: 280px; overflow-y: auto; padding-right: 8px; }}
        .scroll-list.ten-items {{ max-height: 420px; }}
        .link-button {{ display: inline-block; text-decoration: none; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--line); color: var(--text); background: #fff; }}
        @media (max-width: 900px) {{ .grid, .toolbar, .test-toolbar, .test-action-row, .actions, .stats-grid, .answer-actions, .lists {{ grid-template-columns: 1fr; }} .tool-button {{ min-width: 0; }} .page {{ width: min(100vw - 20px, 1180px); }} }}
    </style>
</head>
<body>
    <main class="page">
        <section class="hero">
            <h1>Vocabulary Exercise Web</h1>
            <p>浏览器即可使用的词汇练习器，保留多词库、错题本、艾宾浩斯复习和统计功能。</p>
        </section>
        <section class="flash-list">{flash_html}</section>
        <section class="grid">
            <div class="panel">
                <h2>词库与测试</h2>
                <div class="group-card compact-controls toolbar-strip" id="test-controls">
                    <h3>测试</h3>
                    <div class="test-toolbar">
                        <div class="tool-field">
                            <label for="library_name">当前词库</label>
                            <form method="post" action="/library/select" id="library-select-form">
                                <select id="library_name" name="library_name">{library_options}</select>
                            </form>
                        </div>
                        <div class="tool-field">
                            <label for="test_quantity">测试数量</label>
                            <form method="post" action="/quiz/start" id="quiz-start-form">
                                <input id="test_quantity" name="test_quantity" type="number" min="1" max="{total_words}" value="10">
                            </form>
                        </div>
                        <div>
                            <button type="submit" form="library-select-form" class="secondary tool-button">切换词库</button>
                        </div>
                    </div>
                    <div class="test-action-row">
                        <div>
                            <button type="submit" form="quiz-start-form" class="tool-button">开始测试</button>
                        </div>
                        <div>
                            <form method="post" action="/quiz/reset"><button type="submit" class="warn tool-button">重置当前测试</button></form>
                        </div>
                    </div>
                </div>
                <div id="quiz-section">
                    <div class="{quiz_shell_class}">
                        <div class="quiz-shell-head">
                            <h3 style="margin-bottom: 0;">答题区</h3>
                            <span class="quiz-badge">{quiz_state_label}</span>
                        </div>
                        {quiz_html}
                    </div>
                </div>
                <div class="lists">
                    <div class="list-card"><h3>本轮已学习：{learned_count}</h3><div class="scroll-list ten-items"><ul class="clean">{learned_items}</ul></div></div>
                    <div class="list-card"><div style="display: flex; justify-content: space-between; gap: 12px; align-items: center;"><h3 style="margin-bottom: 0;">本轮错题：{unknown_count}</h3><a href="/wrong_words/export" class="link-button">导出错题</a></div><div class="scroll-list ten-items" style="margin-top: 12px;"><ul class="clean">{unknown_items}</ul></div></div>
                </div>
                <details class="group-card compact-controls collapsible" id="library-management">
                    <summary>词库管理</summary>
                    <div class="collapsible-body">
                        <div class="toolbar" style="grid-template-columns: 1.2fr 1fr 1fr;">
                            <div>
                                <label for="csv_file">上传 CSV</label>
                                <input id="csv_file" name="csv_file" type="file" accept=".csv" form="upload-form">
                            </div>
                            <div style="align-self: end;">
                                <form method="post" action="/library/import_builtin"><button type="submit" class="secondary">导入内置词库</button></form>
                            </div>
                            <div style="align-self: end;">
                                <form id="upload-form" method="post" action="/library/import_upload" enctype="multipart/form-data"><button type="submit" class="secondary">导入上传文件</button></form>
                            </div>
                        </div>
                        <div class="actions" style="margin-top: 12px;">
                            <form method="get" action="/library/export"><button type="submit" class="secondary">导出当前词库</button></form>
                            <div></div>
                            <form method="post" action="/library/clear" onsubmit="return confirm('确认清空当前词库及其错题记录吗？');"><button type="submit" class="danger">清空当前词库</button></form>
                        </div>
                    </div>
                </details>
            </div>
            <div class="panel">
                <h2>统计与记录</h2>
                <div class="stats-grid">{stat_html}</div>
                <div class="list-card" style="margin-top: 18px;"><h3>最近首次测试记录</h3><div class="scroll-list"><ul class="clean">{first_test_items}</ul></div></div>
                <div class="list-card" style="margin-top: 18px;"><h3>错题本</h3><div class="scroll-list"><ul class="clean">{wrong_items}</ul></div></div>
            </div>
        </section>
    </main>
    {smooth_scroll_script}
</body>
</html>"""


class VocabularyHandler(BaseHTTPRequestHandler):
    session_cookie_header = None

    def do_GET(self):
        ensure_all_libraries()
        session_state = get_session_state(self)
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_html(render_page(session_state))
            return

        if parsed.path == "/library/export":
            self.handle_export_library(session_state)
            return

        if parsed.path == "/wrong_words/export":
            self.handle_export_wrong_words(session_state)
            return

        self.send_error(404)

    def do_POST(self):
        ensure_all_libraries()
        session_state = get_session_state(self)
        parsed = urlparse(self.path)
        fields = self.read_post_fields()

        if parsed.path == "/library/select":
            self.handle_select_library(session_state, fields)
        elif parsed.path == "/library/import_builtin":
            self.handle_import_builtin(session_state)
        elif parsed.path == "/library/import_upload":
            self.handle_import_upload(session_state, fields)
        elif parsed.path == "/library/clear":
            self.handle_clear_library(session_state)
        elif parsed.path == "/quiz/start":
            self.handle_start_quiz(session_state, fields)
        elif parsed.path == "/quiz/answer":
            self.handle_answer_quiz(session_state, fields)
        elif parsed.path == "/quiz/next":
            self.handle_next_quiz(session_state)
        elif parsed.path == "/quiz/reset":
            self.handle_reset_quiz(session_state)
        else:
            self.send_error(404)

    def read_post_fields(self):
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        content_type = self.headers.get("Content-Type", "")
        body = self.rfile.read(content_length) if content_length else b""

        if content_type.startswith("multipart/form-data"):
            return parse_multipart(content_type, body)

        parsed = parse_qs(body.decode("utf-8", errors="ignore"))
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def redirect(self, location="/"):
        self.send_response(303)
        if self.session_cookie_header:
            self.send_header("Set-Cookie", self.session_cookie_header)
            self.session_cookie_header = None
        self.send_header("Location", location)
        self.end_headers()

    def send_html(self, content):
        data = content.encode("utf-8")
        self.send_response(200)
        if self.session_cookie_header:
            self.send_header("Set-Cookie", self.session_cookie_header)
            self.session_cookie_header = None
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, filename, content_type, data):
        self.send_response(200)
        if self.session_cookie_header:
            self.send_header("Set-Cookie", self.session_cookie_header)
            self.session_cookie_header = None
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_select_library(self, session_state, fields):
        library_name = fields.get("library_name", DEFAULT_LIBRARY_NAME)
        if library_name not in LIBRARY_TABLES:
            add_flash(session_state, "error", "无效的词库选择。")
        else:
            session_state["library_name"] = library_name
            reset_quiz_state(session_state)
            add_flash(session_state, "success", f"当前词库已切换为：{library_name}")
        self.redirect("/#test-controls")

    def handle_import_builtin(self, session_state):
        library_name = get_library_name(session_state)
        file_path = BUILTIN_LIBRARY_FILES.get(library_name)
        if file_path is None or not file_path.exists():
            add_flash(session_state, "error", "当前词库没有对应的内置词库文件。")
        else:
            imported_count = import_new_words(str(file_path), get_table_name(session_state))
            add_flash(session_state, "success", f"已从内置词库导入 {imported_count} 个单词到 {library_name}。")
        self.redirect("/#library-management")

    def handle_import_upload(self, session_state, fields):
        upload = fields.get("csv_file")
        if not upload or not upload.get("filename"):
            add_flash(session_state, "error", "请选择要导入的 CSV 文件。")
            self.redirect("/#library-management")
            return

        temp_path = BASE_DIR / "_upload_temp.csv"
        temp_path.write_bytes(upload["content"])
        try:
            imported_count = import_new_words(str(temp_path), get_table_name(session_state))
        except Exception as exc:
            add_flash(session_state, "error", f"导入词库失败：{exc}")
        else:
            add_flash(session_state, "success", f"成功导入 {imported_count} 个单词。")
        finally:
            if temp_path.exists():
                temp_path.unlink()
        self.redirect("/#library-management")

    def handle_clear_library(self, session_state):
        clear_up_db(get_table_name(session_state))
        reset_quiz_state(session_state)
        add_flash(session_state, "success", f"已清空 {get_library_name(session_state)}。")
        self.redirect("/#library-management")

    def handle_start_quiz(self, session_state, fields):
        table_name = get_table_name(session_state)
        vocabulary_count = get_library_word_count(table_name)
        try:
            test_quantity = int(fields.get("test_quantity", "0"))
        except ValueError:
            test_quantity = 0

        if vocabulary_count == 0:
            add_flash(session_state, "error", "当前词库没有单词，请先导入词库。")
            self.redirect("/#quiz-section")
            return

        if test_quantity < 1 or test_quantity > vocabulary_count:
            add_flash(session_state, "error", f"测试数量必须在 1 到 {vocabulary_count} 之间。")
            self.redirect("/#quiz-section")
            return

        quiz_words = get_words_for_test(table_name, test_quantity)
        reset_quiz_state(session_state)
        session_state["quiz_words"] = quiz_words
        session_state["quiz_index"] = 0

        if not quiz_words:
            add_flash(session_state, "error", "当前词库没有可用测试单词。")
        else:
            add_flash(session_state, "success", f"已开始测试，共 {len(quiz_words)} 个单词。")
            session_state["smooth_scroll_target"] = "quiz-section"
        self.redirect("/")

    def handle_answer_quiz(self, session_state, fields):
        quiz_words = session_state.get("quiz_words", [])
        quiz_index = session_state.get("quiz_index", 0)
        if quiz_index >= len(quiz_words):
            add_flash(session_state, "error", "当前没有进行中的测试。")
            self.redirect("/#quiz-section")
            return

        answer = fields.get("answer")
        is_known = answer == "known"
        word = quiz_words[quiz_index]
        session_state.setdefault("learned_words", []).append(word["english"])
        result = record_practice_result(get_table_name(session_state), word["english"], is_known)

        if not is_known:
            session_state.setdefault("unknown_words", []).append(f"{word['english']} - {word['chinese'] or '未填写释义'}")

        session_state["quiz_index"] = quiz_index + 1
        session_state["pending_result"] = {
            "english": word["english"],
            "chinese": word["chinese"],
            "is_known": is_known,
            "next_review_date": (result or {}).get("next_review_date", ""),
            "is_finished": session_state["quiz_index"] >= len(quiz_words),
        }

        self.redirect("/#quiz-section")

    def handle_next_quiz(self, session_state):
        pending_result = session_state.get("pending_result")
        session_state["pending_result"] = None
        if pending_result and pending_result.get("is_finished"):
            add_flash(session_state, "success", "本轮测试已完成。")
        self.redirect("/#quiz-section")

    def handle_reset_quiz(self, session_state):
        reset_quiz_state(session_state)
        add_flash(session_state, "success", "已重置当前测试。")
        self.redirect("/#quiz-section")

    def handle_export_library(self, session_state):
        library_name = get_library_name(session_state)
        temp_path = BASE_DIR / "_export_temp.csv"
        export_vocabulary_db(get_table_name(session_state), str(temp_path))
        data = temp_path.read_bytes()
        temp_path.unlink(missing_ok=True)
        self.send_bytes(f"{library_name}.csv", "text/csv; charset=utf-8", data)

    def handle_export_wrong_words(self, session_state):
        unknown_words = session_state.get("unknown_words", [])
        if not unknown_words:
            add_flash(session_state, "error", "当前没有本轮错题可导出。")
            self.redirect("/#quiz-section")
            return

        data = "\n".join(unknown_words).encode("utf-8")
        self.send_bytes("wrong_words.txt", "text/plain; charset=utf-8", data)


def run_server():
    ensure_all_libraries()
    server = ThreadingHTTPServer((HOST, PORT), VocabularyHandler)
    print(f"Vocabulary Exercise Web is running at http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()