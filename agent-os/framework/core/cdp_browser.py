"""CDP Browser Control — Node.js subprocess + CDP 协议操作 Chrome

所有操作通过临时 .mjs 脚本交由 Node.js 执行，避免 Windows Python WebSocket 兼容性问题。
CDP 端口硬编码 127.0.0.1:9333（用户日常 Chrome 远程调试端口）。
注意：PM2环境下stdout捕获不可靠，使用临时文件传递结果。
"""

import html as _html
import json
import os
import subprocess
import tempfile
import time
import urllib.request

CDP_HOST = "127.0.0.1"
CDP_PORT = 9333
TIMEOUT = 30

_FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # framework/
_TEMP_DIR = os.path.join(_FRAMEWORK_ROOT, ".cdp_scripts")
os.makedirs(_TEMP_DIR, exist_ok=True)


# ── 内部工具 ────────────────────────────────────────────────────


def _write_mjs(name: str, code: str) -> str:
    """写入临时 .mjs 文件，返回路径"""
    path = os.path.join(_TEMP_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    return path


def _run_node(mjs_path: str, timeout: int = TIMEOUT) -> str:
    """运行 Node.js 脚本（Windows PM2 兼容：用文件传结果）"""
    out_path = mjs_path.replace(".mjs", ".out.json")
    try:
        with open(mjs_path, "r", encoding="utf-8") as f:
            code = f.read()
        write_out = f'\nconst _fs = await import("fs");\n_fs.default.writeFileSync({json.dumps(out_path)}, _result, "utf-8");\n'
        code = code.replace("ws.close();", write_out + "\nws.close();")
        with open(mjs_path, "w", encoding="utf-8") as f:
            f.write(code)

        subprocess.run(
            ["node", mjs_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_FRAMEWORK_ROOT,
        )
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                output = f.read().strip()
            os.remove(out_path)
            return output
        raise RuntimeError(f"no_output_file rc=0 out={out_path}")
    except subprocess.TimeoutExpired:
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                output = f.read().strip()
            os.remove(out_path)
            if output:
                return output
        raise RuntimeError(f"timeout={timeout}s")


def _cdp_json() -> list[dict]:
    """获取 Chrome DevTools Protocol 页面列表"""
    url = f"http://{CDP_HOST}:{CDP_PORT}/json"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode())


def _js_str(s: str) -> str:
    """Python 字符串 → 安全的 JavaScript 字符串字面量（用于嵌入 .mjs）"""
    return json.dumps(s)


def _build_script(ws_url: str, body: str) -> str:
    """构建完整 .mjs 脚本内容"""
    return f"""const WebSocket = (await import("ws")).default;

const WS_URL = {_js_str(ws_url)};

const ws = new WebSocket(WS_URL);
await new Promise((res, rej) => {{ ws.on("open", res); ws.on("error", rej); }});

let _mid = 0;
function cdp(method, params) {{
    return new Promise((resolve, reject) => {{
        const id = ++_mid;
        const timer = setTimeout(() => reject(new Error("CDP timeout: " + method)), 25000);
        ws.send(JSON.stringify({{id, method, params}}));
        const handler = (data) => {{
            const msg = JSON.parse(data.toString());
            if (msg.id === id) {{
                clearTimeout(timer);
                ws.removeListener("message", handler);
                resolve(msg);
            }}
        }};
        ws.on("message", handler);
    }});
}}

function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}

let _result = "";
try {{
    {body}
}} catch(e) {{
    _result = JSON.stringify({{error: e.message}});
}}
ws.close();
"""


# ── 公共 API ────────────────────────────────────────────────────


def connect_cdp() -> dict:
    """测试 CDP 连接是否正常"""
    try:
        pages = _cdp_json()
        return {"success": True, "pages": len(pages)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def find_tab(keyword: str) -> dict | None:
    """在 Chrome 标签页中查找 URL 或标题匹配关键字的页面"""
    pages = _cdp_json()
    for p in pages:
        url = p.get("url", "")
        title = p.get("title", "")
        if keyword.lower() in url.lower() or keyword.lower() in title.lower():
            return {
                "ws": p["webSocketDebuggerUrl"],
                "title": title,
                "url": url,
                "id": p.get("id"),
            }
    return None


def run_js(keyword: str, js_code: str) -> dict:
    """在匹配关键字的标签页中执行任意 JavaScript"""
    tab = find_tab(keyword)
    if not tab:
        raise RuntimeError(f"标签页未找到，关键字: {keyword}")

    body = f"""await cdp("Page.enable");
await sleep(500);
const r = await cdp("Runtime.evaluate", {{
    expression: {_js_str(js_code)},
    returnByValue: true,
    timeout: 20000,
}});
if (r.result?.exceptionDetails) {{
    _result = JSON.stringify({{error: r.result.exceptionDetails.text}});
}} else {{
    _result = JSON.stringify({{result: r.result?.result?.value}});
}}"""

    script = _build_script(tab["ws"], body)
    name = f"runjs_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def read_upwork_messages(tab_keyword: str = "upwork.com/ab/messages/rooms/") -> dict:
    """读取 Upwork 当前对话消息"""
    tab = find_tab(tab_keyword)
    if not tab:
        tab = find_tab("upwork.com/ab/messages")
    if not tab:
        raise RuntimeError("未找到 Upwork 标签页")

    body = """await cdp("Page.enable");
await sleep(2000);
const r = await cdp("Runtime.evaluate", {
    expression: "document.body?.innerText || ''",
    returnByValue: true,
    timeout: 15000,
});
const text = r.result?.result?.value || '';
const startIdx = text.indexOf('Messages');
const endIdx = text.lastIndexOf('Write a message');
const messages = startIdx >= 0
    ? text.substring(startIdx, endIdx > startIdx ? endIdx : undefined)
    : text.substring(0, endIdx > 0 ? endIdx : undefined);
_result = JSON.stringify({content: messages.substring(0, 8000), totalLength: text.length});
"""

    script = _build_script(tab["ws"], body)
    name = f"upread_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def send_upwork_message(text: str, tab_keyword: str = "upwork.com/ab/messages/rooms/") -> dict:
    """向 Upwork 当前对话发送消息"""
    tab = find_tab(tab_keyword)
    if not tab:
        tab = find_tab("upwork.com/ab/messages")
    if not tab:
        raise RuntimeError("未找到 Upwork 消息标签页")

    lines = text.split("\n")
    inner_html = "".join(f"<p>{_html.escape(l)}</p>" for l in lines)

    set_content_js = (
        "(function(){"
        "var ed=document.querySelector('.tiptap.ProseMirror');"
        "if(!ed)return'EDITOR_NOT_FOUND';"
        "ed.focus();"
        f"ed.innerHTML={_js_str(inner_html)};"
        "ed.dispatchEvent(new Event('input',{bubbles:true}));"
        "return'OK';"
        "})()"
    )

    body = f"""await cdp("Page.enable");
await sleep(1500);

// Step 1: Focus editor + set innerHTML
var r = await cdp("Runtime.evaluate", {{
    expression: {_js_str(set_content_js)},
    returnByValue: true,
}});
var editorStatus = r.result?.result?.value;

await sleep(800);

// Step 2: Dispatch Enter key to trigger Upwork send
await cdp("Input.dispatchKeyEvent", {{type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13}});
await cdp("Input.dispatchKeyEvent", {{type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13}});

await sleep(2000);

// Step 3: Verify
r = await cdp("Runtime.evaluate", {{
    expression: "JSON.stringify({{composerEmpty:(document.querySelector('.composer')?.innerText?.trim()||'')===''}})",
    returnByValue: true,
}});
var verifyRaw = r.result?.result?.value;

_result = JSON.stringify({{status:"sent", editorStatus, textLength:{len(text)}, verify:verifyRaw}});
"""

    script = _build_script(tab["ws"], body)
    name = f"upsend_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ── Fiverr 支持 ──────────────────────────────────────────────────


def read_fiverr_messages(tab_keyword: str = "fiverr.com/inbox") -> dict:
    """读取 Fiverr 当前对话消息"""
    tab = find_tab(tab_keyword)
    if not tab:
        tab = find_tab("fiverr.com")
    if not tab:
        raise RuntimeError("未找到 Fiverr 标签页")

    body = """await cdp("Page.enable");
await sleep(2000);
const r = await cdp("Runtime.evaluate", {
    expression: "document.body?.innerText || ''",
    returnByValue: true,
    timeout: 15000,
});
const text = r.result?.result?.value || '';
const startIdx = text.indexOf('Inbox');
const endIdx = text.lastIndexOf('Type a message');
const messages = startIdx >= 0
    ? text.substring(startIdx, endIdx > startIdx ? endIdx : undefined)
    : text.substring(0, endIdx > 0 ? endIdx : undefined);
_result = JSON.stringify({content: messages.substring(0, 8000), totalLength: text.length});
"""

    script = _build_script(tab["ws"], body)
    name = f"fivread_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def send_fiverr_message(text: str, tab_keyword: str = "fiverr.com/inbox") -> dict:
    """向 Fiverr 当前对话发送消息"""
    tab = find_tab(tab_keyword)
    if not tab:
        tab = find_tab("fiverr.com")
    if not tab:
        raise RuntimeError("未找到 Fiverr 标签页")

    lines = text.split("\n")
    inner_html = "".join(f"<p>{_html.escape(l)}</p>" for l in lines)

    set_content_js = (
        "(function(){"
        "var ed=document.querySelector('[contenteditable=\"true\"]');"
        "if(!ed)return'EDITOR_NOT_FOUND';"
        "ed.focus();"
        f"ed.innerHTML={_js_str(inner_html)};"
        "ed.dispatchEvent(new Event('input',{bubbles:true}));"
        "return'OK';"
        "})()"
    )

    body = f"""await cdp("Page.enable");
await sleep(1500);

// Step 1: Focus editor + set innerHTML
var r = await cdp("Runtime.evaluate", {{
    expression: {_js_str(set_content_js)},
    returnByValue: true,
}});
var editorStatus = r.result?.result?.value;

await sleep(800);

// Step 2: Find and click Send button
r = await cdp("Runtime.evaluate", {{
    expression: `(function(){{
        var btn = document.querySelector('[data-test="send-message"]') ||
                  document.querySelector('[class*="send" i] button') ||
                  document.querySelector('button[type="submit"]');
        if(!btn) return 'SEND_BTN_NOT_FOUND';
        btn.click();
        return 'OK';
    }})()`,
    returnByValue: true,
}});
var sendResult = r.result?.result?.value;

await sleep(2000);

// Step 3: Verify
r = await cdp("Runtime.evaluate", {{
    expression: "JSON.stringify({{sent:(sendResult==='OK'), editorStatus, sendResult}})",
    returnByValue: true,
}});
var verifyRaw = r.result?.result?.value;

_result = JSON.stringify({{status:"sent", editorStatus, textLength:{len(text)}, verify:verifyRaw}});
"""

    script = _build_script(tab["ws"], body)
    name = f"fivsend_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ── 主动找活 ─────────────────────────────────────────────────────


def search_upwork_jobs(search_term: str = "web scraping python AI", limit: int = 15) -> dict:
    """搜索 Upwork 最新岗位（在自动化tab内导航，不碰用户tab）"""
    import urllib.parse

    encoded = urllib.parse.quote(search_term)
    target_url = f"https://www.upwork.com/nx/search/jobs/?q={encoded}&sort=recency"

    # 找自动创建的messages tab（不是用户手动开的）
    tab = find_tab("upwork.com/ab/messages/rooms/") or find_tab("upwork.com/ab/messages")
    if not tab:
        return {"success": False, "error": "No Upwork messages tab found - user might not be logged in"}

    body = '''
const targetUrl = {TARGET_URL};
const messagesUrl = "https://www.upwork.com/ab/messages/rooms/";

await cdp("Page.enable");
await cdp("Page.navigate", {url: targetUrl});

await sleep(6000);
let maxWait = 30;
while (maxWait-- > 0) {
    const r = await cdp("Runtime.evaluate", {
        expression: "document.querySelector('[data-test*=\\"job-tile\\"],[data-test*=\\"job-card\\"],article') ? 'OK' : document.readyState === 'complete' ? 'LOADED' : 'WAIT'",
        returnByValue: true,
    });
    if (r.result?.result?.value === 'OK') break;
    await sleep(1000);
}
await sleep(4000);

const jobData = await cdp("Runtime.evaluate", {
    expression: `(function() {
        const cards = document.querySelectorAll('[data-test*=\\"job-tile\\"],[data-test*=\\"job-card\\"],article[data-test*=\\"job\\"],[data-job-category]');
        if (!cards.length) {
            const body = document.body?.innerText || '';
            const lines = body.split('\\n').filter(l => l.trim());
            const jobs = [];
            for (let i = 0; i < lines.length && jobs.length < {LIMIT}; i++) {
                if (lines[i].length > 10 && lines[i].length < 200 && !lines[i].includes('Sign') && !lines[i].includes('Log')) {
                    jobs.push({title: lines[i].substring(0, 200), text: (lines[i+1]||'').substring(0, 300)});
                }
            }
            return {jobs, fallback: true, pageTextLength: body.length};
        }
        return {
            jobs: Array.from(cards).slice(0, {LIMIT}).map(card => ({
                title: (card.querySelector('[class*="title" i],[data-test*="title"],[data-test*="job-title"]')?.innerText || '').trim(),
                description: (card.querySelector('[class*="description" i],[data-test*="description"],[data-test*="desc"]')?.innerText || '').substring(0, 300).trim(),
                budget: (card.querySelector('[class*="budget" i],[data-test*="budget"],[data-test*="price"]')?.innerText || '').trim(),
                skills: Array.from(card.querySelectorAll('[class*="skill" i],[data-test*="skill"]')).map(s => s.innerText.trim()).join(', '),
                proposals: (card.querySelector('[class*="proposals" i],[data-test*="proposals"],[data-test*="proposal"]')?.innerText || '').trim(),
                payment: (card.querySelector('[class*="payment" i],[data-test*="payment"],[class*="verified"]')?.innerText || '').trim(),
                link: card.querySelector('a[href*="job"]')?.href || '',
            })),
            fallback: false,
        };
    })()`,
    returnByValue: true,
    timeout: 20000,
});
const raw = jobData.result?.result?.value || {};
const jobs = Array.isArray(raw.jobs) ? raw.jobs : [];

await cdp("Page.navigate", {url: messagesUrl});

_result = JSON.stringify({count: jobs.length, jobs, searchTerm: {ST}, url: {TARGET_URL_JSON}, fallback: raw.fallback});
'''.replace('{TARGET_URL}', _js_str(target_url)).replace('{TARGET_URL_JSON}', _js_str(target_url)).replace('{ST}', _js_str(search_term)).replace('{LIMIT}', str(limit))

    script = _build_script(tab["ws"], body)
    name = f"upsearch_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path, timeout=90)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def search_fiverr_opportunities(search_term: str = "", limit: int = 10) -> dict:
    """搜索 Fiverr 机会（Seller Briefs / 买家需求）"""
    import urllib.parse

    tab = find_tab("fiverr.com")
    if not tab:
        raise RuntimeError("未找到 Fiverr 标签页")

    url = "https://www.fiverr.com/users/mfeng/seller_dashboard"
    if search_term:
        url += f"?search={urllib.parse.quote(search_term)}"

    body = f"""
const targetUrl = {_js_str(url)};
await cdp("Page.enable");
await cdp("Page.navigate", {{url: targetUrl}});
await sleep(4000);

let maxWait = 20;
while (maxWait-- > 0) {{
    const r = await cdp("Runtime.evaluate", {{
        expression: "document.readyState === 'complete' ? 'OK' : 'WAIT'",
        returnByValue: true,
    }});
    if (r.result?.result?.value === 'OK') break;
    await sleep(1000);
}}
await sleep(3000);

const pageInfo = await cdp("Runtime.evaluate", {{
    expression: `(function() {{
        const briefs = document.querySelectorAll('[class*="brief" i],[class*="request" i],[data-test*="brief"],[data-test*="request"]');
        const opportunities = Array.from(briefs).slice(0, {limit}).map(el => ({{
            title: el.querySelector('[class*="title" i]')?.innerText || '',
            text: el.innerText.substring(0, 300),
        }}));
        const mainText = document.body?.innerText?.substring(0, 3000) || '';
        return {{
            opportunities,
            pageTitle: document.title,
            mainTextSnippet: mainText,
            url: window.location.href,
        }};
    }})()`,
    returnByValue: true,
    timeout: 15000,
}});
const info = pageInfo.result?.result?.value || {{}};
_result = JSON.stringify({{success: true, searchTerm: {_js_str(search_term)}, ...info}});
"""

    script = _build_script(tab["ws"], body)
    name = f"fivsearch_{int(time.time()*1000)}.mjs"
    path = _write_mjs(name, script)
    try:
        out = _run_node(path, timeout=45)
        return json.loads(out)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def close(_ws_url: str = "") -> dict:
    """CDP 连接关闭（单操作模式无需持久连接，保留接口签名一致性）"""
    return {"status": "ok", "note": "每个操作独立连接，无需显式关闭"}
