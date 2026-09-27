#!/usr/bin/env python3
"""Minimal Chrome DevTools Protocol driver for Apple/Firebase web consoles that have no API for a step.

Why (09/27/2026): App Store Connect cannot CREATE an app record through its API (403 "does not allow 'CREATE'"), and
the APNs key / Firebase steps are web-only. Joe: "you can run crome headless". This drives a real headless Chrome.

Secrets rules (memory rules/secrets-and-access.md): a password is only ever sent with Input.insertText into a field that
was verified as type=password first; no screenshot/DOM dump is taken while a secret is in a field; values are never
printed. The browser profile lives on tmpfs ($XDG_RUNTIME_DIR) and is deleted after.

Usage as a library:  from cdp import Chrome;  c = Chrome(); c.goto(url); c.frames(); c.eval(js, frame=...)
"""
import json, os, subprocess, time, urllib.request
import websocket

RUNDIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "apple")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")


class Chrome:
    def __init__(self, port=9333, profile=None):
        self.port = port
        self.profile = profile or os.path.join(RUNDIR, "chrome")
        os.makedirs(self.profile, mode=0o700, exist_ok=True)
        self.proc = subprocess.Popen(
            ["google-chrome", "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={self.profile}",
             "--no-first-run", "--no-default-browser-check", "--window-size=1366,900", f"--user-agent={UA}",
             "--disable-blink-features=AutomationControlled", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                page = [t for t in tabs if t["type"] == "page"][0]
                break
            except Exception:
                time.sleep(0.2)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=60, suppress_origin=True)
        self.i = 0
        self.sessions = {}          # frame url substring -> sessionId (out-of-process iframes)
        self.send("Page.enable"); self.send("Runtime.enable")
        self.send("Target.setAutoAttach", autoAttach=True, waitForDebuggerOnStart=False, flatten=True)

    def send(self, method, session=None, **params):
        self.i += 1; my = self.i        # send_nowait() below bumps self.i - wait for OUR id, not the latest
        msg = {"id": my, "method": method, "params": params}
        if session: msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("method") == "Target.attachedToTarget":
                ti = r["params"]["targetInfo"]; sid = r["params"]["sessionId"]
                self.sessions[ti.get("url", "")] = sid
                self.send_nowait("Runtime.enable", sid)
            if r.get("id") == my:
                if "error" in r: raise RuntimeError(f"{method}: {r['error']}")
                return r.get("result", {})

    def send_nowait(self, method, session=None, **params):
        self.i += 1
        msg = {"id": self.i, "method": method, "params": params}
        if session: msg["sessionId"] = session
        self.ws.send(json.dumps(msg))

    def goto(self, url, wait=6):
        self.send("Page.navigate", url=url); time.sleep(wait)

    def frame(self, needle):
        """sessionId of the out-of-process iframe whose URL contains needle (e.g. 'idmsa.apple.com')."""
        self.send("Runtime.evaluate", expression="1")          # pump events so attach messages are read
        for u, sid in self.sessions.items():
            if needle in u: return sid
        return None

    def frame_ctx(self, needle):
        """Execution-context id inside an IN-PROCESS iframe whose URL contains needle (headless Chrome keeps Apple's
        idmsa sign-in frame in-process, so there is no separate target to attach to - 09/27/2026)."""
        tree = self.send("Page.getFrameTree")["frameTree"]
        stack = [tree]
        while stack:
            n = stack.pop(); f = n["frame"]
            if needle in f.get("url", ""):
                return self.send("Page.createIsolatedWorld", frameId=f["id"], worldName="wa0o",
                                 grantUniveralAccess=True)["executionContextId"]
            stack += n.get("childFrames", [])
        return None

    def eval(self, js, session=None, ctx=None):
        p = dict(expression=js, returnByValue=True, awaitPromise=True)
        if ctx: p["contextId"] = ctx
        r = self.send("Runtime.evaluate", session, **p)
        if "exceptionDetails" in r: return None
        return r.get("result", {}).get("value")

    def insert_secret(self, selector, value, session=None, ctx=None):
        """Focus selector, VERIFY it is a password field, then insert value without echo."""
        t = self.eval(f"(()=>{{const e=document.querySelector({json.dumps(selector)}); if(!e) return 'missing';"
                      f"e.focus(); return e.type;}})()", session, ctx)
        if t != "password": raise RuntimeError(f"refusing to type a secret: {selector} is '{t}', not a password field")
        self.send("Input.insertText", session, text=value)

    def insert_text(self, selector, value, session=None, ctx=None):
        ok = self.eval(f"(()=>{{const e=document.querySelector({json.dumps(selector)}); if(!e) return false;"
                       f"e.focus(); return true;}})()", session, ctx)
        if not ok: raise RuntimeError(f"field not found: {selector}")
        self.send("Input.insertText", session, text=value)

    def key(self, key="Enter", session=None):
        """A TRUSTED key press (Input domain). Apple's sign-in ignores element.click() from script (09/27)."""
        vk = 13 if key == "Enter" else 0
        self.send("Input.dispatchKeyEvent", session, type="keyDown", key=key, code=key, windowsVirtualKeyCode=vk,
                  nativeVirtualKeyCode=vk, text="\r" if key == "Enter" else "")
        self.send("Input.dispatchKeyEvent", session, type="keyUp", key=key, code=key, windowsVirtualKeyCode=vk,
                  nativeVirtualKeyCode=vk)

    def shot(self, path):
        import base64
        d = self.send("Page.captureScreenshot", format="png")["data"]
        open(path, "wb").write(base64.b64decode(d)); return path

    def close(self):
        try: self.send("Browser.close")
        except Exception: pass
        self.proc.wait(timeout=10)
