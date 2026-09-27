#!/usr/bin/env python3
"""Sign in to App Store Connect in headless Chrome, wait for Joe's 2FA code, then stop at a signed-in session.
Later steps (create app record, APNs key) are separate functions run in the same browser.

Joe 09/27/2026: "you can run crome headless the un and password is in t: as apple.txt and ill do the 2fa token from
apple the same way". Credentials: $XDG_RUNTIME_DIR/apple/apple.txt (line1 Apple ID, line2 password; moved off T: and
shredded there). 2FA: Joe drops the 6 digits in T:\\apple-2fa.txt -> /mnt/fs01-transfer/apple-2fa.txt (read, shredded).
Log: $XDG_RUNTIME_DIR/apple/run.log; screenshots only where no secret is on screen: ~/wa0o-ad/.shots/apple-*.png
"""
import os, sys, time, json, subprocess
sys.path.insert(0, os.path.dirname(__file__))
from cdp import Chrome, RUNDIR

LOG = os.path.join(RUNDIR, "run.log")
SHOTS = os.path.expanduser("~/wa0o-ad/.shots")
CODEFILE = "/mnt/fs01-transfer/apple-2fa.txt"

def log(*a):
    with open(LOG, "a") as f: f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")

def wait_for(c, js, where=None, secs=40, what=""):
    for _ in range(secs):
        v = c.eval(js, ctx=where[1]) if isinstance(where, tuple) else c.eval(js, where)
        if v: return v
        time.sleep(1)
    log("TIMEOUT waiting for", what); return None

def ctx(c):
    for _ in range(30):
        x = c.frame_ctx("idmsa.apple.com")
        if x: return x
        time.sleep(1)
    return None

def signin(c):
    cred = os.path.join(RUNDIR, "apple.txt")
    if not os.path.exists(cred):               # Joe re-drops T:\apple.txt -> move to tmpfs 0600, shred the share copy
        log("waiting for T:\\apple.txt")
        src = "/mnt/fs01-transfer/apple.txt"
        for _ in range(1800):
            if os.path.exists(src) and os.path.getsize(src) > 5: break
            time.sleep(1)
        else:
            log("no apple.txt within 30 min"); return False
        time.sleep(2)
        subprocess.run(["install", "-m", "600", src, cred], check=True); subprocess.run(["shred", "-u", src])
        log("apple.txt moved to tmpfs, T: copy shredded")
    apple_id, pw = open(cred).read().splitlines()[:2]
    c.goto("https://appstoreconnect.apple.com/login", wait=10)
    x = ctx(c)
    if not x: log("no idmsa frame"); c.shot(f"{SHOTS}/apple-0-noframe.png"); return False
    log("idmsa frame context", x)
    if not wait_for(c, "!!document.querySelector('#account_name_text_field')", ctx_js(x), what="account field"):
        c.shot(f"{SHOTS}/apple-1-noaccount.png"); return False
    c.insert_text("#account_name_text_field", apple_id, ctx=x)
    c.key("Enter"); log("apple id entered, Enter pressed (trusted)")
    time.sleep(4)
    x = ctx(c)
    c.eval("(()=>{const b=[...document.querySelectorAll('button')].find(e=>/continue with password/i.test(e.innerText)); if(b){b.click(); return 1} return 0})()", ctx=x)
    time.sleep(2)
    if not wait_for(c, "(()=>{const e=document.querySelector('#password_text_field'); return !!(e && e.offsetParent!==null && !e.disabled)})()", ctx_js(x), what="password field"):
        c.shot(f"{SHOTS}/apple-2-nopw.png"); return False
    c.insert_secret("#password_text_field", pw, ctx=x); del pw
    c.key("Enter")
    log("password submitted with trusted Enter (field verified type=password)")
    time.sleep(8)
    c.shot(f"{SHOTS}/apple-3-after-password.png")
    return True

def ctx_js(x):
    return ("ctx", x)

def two_factor(c):
    n = 0
    for _ in range(25):
        x = ctx(c)
        n = c.eval("document.querySelectorAll('input.form-security-code-input, input[id^=char], input[autocomplete=one-time-code]').length", ctx=x) or 0
        if n: break
        time.sleep(1)
    log("2FA inputs:", n)
    if not n: c.shot(f"{SHOTS}/apple-4-no2fa.png"); return False
    log("waiting for Joe's code in T:\\apple-2fa.txt")
    code = ""
    for _ in range(900):                     # 15 min
        if os.path.exists(CODEFILE):
            code = "".join(ch for ch in open(CODEFILE).read() if ch.isdigit())[:6]
            subprocess.run(["shred", "-u", CODEFILE])
            if len(code) == 6: break
            log("code file had", len(code), "digits - waiting for a new one")
        time.sleep(1)
    if len(code) != 6: log("no 2FA code within 15 min"); return False
    x = ctx(c)
    c.eval("(()=>{const e=document.querySelector('input.form-security-code-input, input[id^=char], input[autocomplete=one-time-code]'); e.focus(); return 1})()", ctx=x)
    for ch in code:
        c.send("Input.insertText", text=ch); time.sleep(0.2)
    log("2FA code entered")
    time.sleep(8)
    x = ctx(c)
    if x: c.eval("(()=>{const b=[...document.querySelectorAll('button')].find(e=>/^\\s*trust\\s*$/i.test(e.innerText)); if(b){b.click(); return 1} return 0})()", ctx=x)
    time.sleep(10)
    c.shot(f"{SHOTS}/apple-5-signed-in.png")
    log("url now:", c.eval("location.href"))
    return True

if __name__ == "__main__":
    open(LOG, "w").close()
    headed = os.environ.get("HEADED") == "1"   # 09/27: headless sign-in stalls after the password -> try a real window
    c = Chrome(headless=not headed)
    try:
        if signin(c) and two_factor(c):
            log("SIGNED IN - keeping the browser up for the next steps (port 9333)")
            open(os.path.join(RUNDIR, "signed-in"), "w").write(str(os.getpid()))
            time.sleep(3600)                 # hold the session for the follow-on steps
    except Exception as e:
        log("ERROR", type(e).__name__, str(e)[:200])
    finally:
        c.close()
