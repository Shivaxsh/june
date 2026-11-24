// June Browser: fixed operations on Google Chrome for Naukri. Only naukri.com addresses open, only
// tabs June opened are touched, and only the page scripts written below ever run. Values reach
// AppleScript as Apple Event parameters of fixed handlers, never as script text.
import AppKit
import Foundation

func emit(_ value: [String:Any]) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject:value) { FileHandle.standardOutput.write(data) }
    exit(value["ok"] as? Bool == true ? 0 : 1)
}
func validURL(_ u:String) -> Bool {
    u.count <= 600 && u.range(of:"^https://(www\\.)?naukri\\.com/[A-Za-z0-9/_.~%=&?+-]*$", options:.regularExpression) != nil
}
func fourCC(_ s:String) -> UInt32 { s.utf8.reduce(0) { ($0 << 8) | UInt32($1) } }

// Facts about a Naukri job page. Read only: nothing is clicked or typed.
let factsJS = """
(() => {
  const t = s => (s || '').replace(/\\s+/g, ' ').trim();
  const shown = e => !!e && e.offsetParent !== null;
  const buttons = [...document.querySelectorAll('button, a')].filter(shown);
  const label = b => t(b.innerText || b.textContent).toLowerCase();
  const find = re => buttons.find(b => re.test(label(b)));
  const apply = document.querySelector('#apply-button') || find(/^apply( now)?$/);
  // "Applied" comes only from Naukri's own apply control. A success sentence counts only inside the job's
  // apply area (never a banner, sidebar or another job's card), and is reported separately.
  const appliedControl = document.querySelector('#already-applied') || find(/^applied$/);
  const area = (appliedControl || apply || document.querySelector('#company-site-button') || document.querySelector('#login-apply-button'));
  const zone = area ? (area.closest('[class*="apply"], [class*="Apply"], [class*="jd-header"], [class*="styles_jhc"], section') || area.parentElement) : null;
  const zoneText = t(zone ? zone.innerText : '').toLowerCase();
  const toast = [...document.querySelectorAll('[role="alert"], [class*="toast"], [class*="Toast"], [class*="apply-message"], [class*="applyMessage"]')].filter(shown).map(e => t(e.innerText).toLowerCase()).join(' ');
  const success = /you have successfully applied|successfully applied|application (has been )?(sent|submitted)/;
  const applied = !!appliedControl;
  const confirmation = success.test(zoneText) || success.test(toast);
  const external = !!(document.querySelector('#company-site-button') || find(/apply on company (site|website)/));
  const login = !!(document.querySelector('#login-apply-button') || find(/^(login|log in|register) to apply$/));
  const drawer = [...document.querySelectorAll('[class*="chatbot"], [class*="Chatbot"]')].find(shown);
  const captcha = !!document.querySelector('iframe[src*="captcha"], [class*="captcha"], [id*="captcha"]');
  // Naukri's closed-job page: "Job you are looking for is expired." (often shown at another address, with similar jobs below).
  const expired = /job you are looking for (is|has) expired|this job (is|has) (expired|been closed)|no longer accepting applications/.test(t(document.body && document.body.innerText).toLowerCase().slice(0, 20000));
  const h1 = document.querySelector('h1');
  const comp = document.querySelector('[class*="comp-name"] a, a[class*="comp-name"], [class*="jd-header-comp-name"] a, [class*="comp-name"]');
  return JSON.stringify({url: location.href, ready: document.readyState, title: t(h1 && h1.innerText).slice(0, 200), company: t(comp && comp.innerText).slice(0, 200),
    apply: !!apply, applyText: apply ? label(apply).slice(0, 40) : '', applied, confirmation, external, login, questions: !!drawer, captcha, expired});
})()
"""
// Press Naukri's own Apply button, only on the reviewed job's own page (checked here, in the same script
// as the click, so a navigation in between cannot redirect it) and only when nothing else is in the way.
// JOB_ID is replaced by the reviewed job id, which is validated as 8–16 digits before it reaches this text.
let clickTemplate = """
(() => {
  const t = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const shown = e => !!e && e.offsetParent !== null;
  const refuse = reason => JSON.stringify({clicked: false, reason});
  const here = (location.pathname.match(/job-listings-[a-z0-9-]*?-(\\d{8,16})\\/?$/i) || [])[1];
  if (location.hostname.replace(/^www\\./, '') !== 'naukri.com' || here !== 'JOB_ID') return refuse('different-job');
  const buttons = [...document.querySelectorAll('button, a')].filter(shown);
  const find = re => buttons.find(b => re.test(t(b.innerText || b.textContent)));
  if (document.querySelector('#already-applied') || find(/^applied$/)) return refuse('already-applied');
  if (document.querySelector('#login-apply-button') || find(/^(login|log in|register) to apply$/)) return refuse('login');
  if (document.querySelector('iframe[src*="captcha"], [class*="captcha"], [id*="captcha"]')) return refuse('captcha');
  if (document.querySelector('#company-site-button') || find(/apply on company (site|website)/)) return refuse('external');
  if ([...document.querySelectorAll('[class*="chatbot"], [class*="Chatbot"]')].some(shown)) return refuse('questions');
  const apply = document.querySelector('#apply-button') || buttons.find(b => b.tagName === 'BUTTON' && /^apply( now)?$/.test(t(b.innerText)));
  if (!shown(apply) || apply.disabled) return refuse('no-apply-button');
  apply.click();
  return JSON.stringify({clicked: true});
})()
"""
// Naukri's recruiter-question box after Apply. Bound to the reviewed job like the click. MODE is "read" (no change),
// "text" (type VALUE in the one answer box) or "option" (click the one option whose label is exactly VALUE).
// Entry happens only while the question on screen is exactly EXPECTED (the question June read and answered);
// Save is clicked ~400 ms later only if the question and the entered answer are still the same, and its outcome
// is reported on the next read as lastSave. Placeholders are filled in one pass with JSON literals (chatJS).
let chatTemplate = #"""
(() => {
  const t = s => (s || '').replace(/\s+/g, ' ').trim();
  const shown = e => !!e && e.offsetParent !== null && getComputedStyle(e).visibility !== 'hidden';
  const out = v => JSON.stringify(v);
  // Checked now and again right before the delayed Save: a page that changes its address without reloading keeps timers alive.
  const sameJob = () => location.protocol === 'https:' && location.hostname.replace(/^www\./, '') === 'naukri.com'
    && (location.pathname.match(/job-listings-[a-z0-9-]*?-(\d{8,16})\/?$/i) || [])[1] === 'JOB_ID';
  if (!sameJob()) return out({ok: false, reason: 'different-job'});
  const MODE = MODE_VALUE, VALUE = VALUE_VALUE, EXPECTED = EXPECTED_VALUE;
  const cls = e => (e.getAttribute && e.getAttribute('class')) || '';
  const success = /you have successfully applied|successfully applied|applied to\s+["\u201c]|application (has been )?(sent|submitted)/i;
  const applied = !!document.querySelector('#already-applied') || success.test(t(document.body.innerText).slice(0, 20000));
  const findDrawer = () => [...document.querySelectorAll('[class*="chatbot"], [class*="Chatbot"]')].filter(shown)
    .sort((a, b) => b.querySelectorAll('*').length - a.querySelectorAll('*').length)[0];
  const questionIn = d => {
    const messages = [...d.querySelectorAll('[class*="botMsg"], [class*="BotMsg"], [class*="bot-msg"], [class*="botItem"]')]
      .filter(e => shown(e) && !e.querySelector('[class*="botMsg"], [class*="BotMsg"]')).map(e => t(e.innerText)).filter(Boolean);
    return (messages[messages.length - 1] || '').slice(0, 400);
  };
  const drawer = findDrawer();
  if (!drawer) return out({ok: true, open: false, applied, lastSave: window.__juneLastSave || null});
  const question = questionIn(drawer);
  const labelOf = i => t((i.id && (drawer.querySelector('label[for="' + CSS.escape(i.id) + '"]') || {}).innerText) || (i.closest('label') || {}).innerText
    || (i.nextElementSibling || {}).innerText || i.value || '');
  // "Skip this question" moves past a question without answering it, in any form (chip, radio or checkbox):
  // it is never offered as an answer and never clicked.
  const navigation = /^skip(\s+this\s+question)?$/i;
  const radios = [...drawer.querySelectorAll('input[type=radio]')].filter(i => !navigation.test(labelOf(i)));
  const checks = [...drawer.querySelectorAll('input[type=checkbox]')].filter(i => !navigation.test(labelOf(i)));
  // Only innermost chips: a wrapper whose class also says "chip" is not an option. Genuine answer chips, including
  // "I'll do it later" for a resume upload, stay; a Skip chip can sit beside a text box and is never an answer.
  const chips = [...drawer.querySelectorAll('[class*="chip"], [class*="Chip"]')]
    .filter(e => shown(e) && !e.querySelector('[class*="chip"], [class*="Chip"]') && e.children.length <= 2 && t(e.innerText) && !navigation.test(t(e.innerText)));
  const texts = [...drawer.querySelectorAll('[contenteditable="true"], textarea, input[type=text], input[type=number], input[type=tel], input[type=email], input:not([type])')].filter(shown);
  const saveButton = d => [...d.querySelectorAll('button, [role=button], div, span')]
    .filter(e => shown(e) && e.children.length <= 2 && (/^(save|send|submit|next|done)$/i.test(t(e.innerText)) || /sendmsg|send-msg|sendbtn/i.test(cls(e)))).pop();
  let kind = 'unknown', options = [];
  if (radios.length) { kind = 'radio'; options = radios.map(labelOf); }
  else if (checks.length) { kind = 'checkbox'; options = checks.map(labelOf); }
  else if (chips.length) { kind = 'chips'; options = chips.map(e => t(e.innerText)); }
  else if (texts.length > 1) kind = 'multi';
  else if (texts.length === 1) kind = texts[0].type === 'number' ? 'number' : 'text';
  options = options.filter(Boolean).slice(0, 12).map(o => o.slice(0, 120));
  if (MODE === 'read') return out({ok: true, open: true, applied, question, kind, options, lastSave: window.__juneLastSave || null});
  // Never enter an answer into a different question than the one it was chosen for.
  if (question !== EXPECTED) return out({ok: true, answered: false, reason: 'question-changed', question});
  let entered = () => true;
  if (MODE === 'text') {
    if (texts.length !== 1) return out({ok: true, answered: false, reason: 'no-text-box'});
    const box = texts[0]; box.focus();
    if (box.isContentEditable) box.innerText = VALUE;
    else Object.getOwnPropertyDescriptor(box.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(box, VALUE);
    box.dispatchEvent(new InputEvent('input', {bubbles: true, data: VALUE, inputType: 'insertText'}));
    box.dispatchEvent(new Event('change', {bubbles: true}));
    box.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
    // The box must still be on the page and inside the live question box (React may replace it).
    entered = () => box.isConnected && !!findDrawer()?.contains(box) && t(box.isContentEditable ? box.innerText : box.value) === t(VALUE);
    if (!entered()) return out({ok: true, answered: false, reason: 'not-entered'});
  } else if (MODE === 'option') {
    const all = [...radios.map(i => [i, labelOf(i)]), ...checks.map(i => [i, labelOf(i)]), ...chips.map(e => [e, t(e.innerText)])];
    const hits = all.filter(([, l]) => l === VALUE);
    if (hits.length !== 1) return out({ok: true, answered: false, reason: 'no-such-option'});
    const [target] = hits[0];
    target.click();
    if (target.tagName === 'INPUT') {
      entered = () => target.isConnected && !!findDrawer()?.contains(target) && target.checked === true;
      if (!entered()) return out({ok: true, answered: false, reason: 'not-entered'});
    }
  } else return out({ok: false, reason: 'mode'});
  window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'pending'};
  // Save after the page has taken the answer in (chips often send themselves) — only for the same question and answer.
  setTimeout(() => {
    if (!sameJob()) { window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'different-job'}; return; }
    const d = findDrawer();
    if (!d) { window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'closed'}; return; }
    if (questionIn(d) !== EXPECTED) { window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'question-changed'}; return; }
    if (!entered()) { window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'answer-changed'}; return; }
    const save = saveButton(d);
    if (save && !save.disabled) { save.click(); window.__juneLastSave = {question: EXPECTED, saved: true}; }
    else window.__juneLastSave = {question: EXPECTED, saved: false, reason: 'no-save-button'};
  }, 400);
  return out({ok: true, answered: true});
})()
"""#
func jsLiteral(_ s:String) -> String? {
    guard let data = try? JSONSerialization.data(withJSONObject:[s]), var text = String(data:data, encoding:.utf8) else { return nil }
    text = String(text.dropFirst().dropLast())
    return text.replacingOccurrences(of:"\u{2028}", with:"\\u2028").replacingOccurrences(of:"\u{2029}", with:"\\u2029")
}
func validAnswer(_ s:String) -> Bool { !s.isEmpty && s.count <= 300 && s.range(of:"[\\x00-\\x1f\\x7f]", options:.regularExpression) == nil }
func validQuestion(_ s:String) -> Bool { !s.isEmpty && s.count <= 400 && s.range(of:"[\\x00-\\x1f\\x7f]", options:.regularExpression) == nil }
/// Fill the template's placeholders in ONE pass, so text substituted for one (e.g. a page's question) can never
/// be mistaken for another placeholder.
func fill(_ template:String, _ values:[String:String]) -> String? {
    guard let pattern = try? NSRegularExpression(pattern:"JOB_ID|MODE_VALUE|EXPECTED_VALUE|VALUE_VALUE") else { return nil }
    var out = "", last = template.startIndex
    for match in pattern.matches(in:template, range:NSRange(template.startIndex..., in:template)) {
        guard let range = Range(match.range, in:template), let value = values[String(template[range])] else { return nil }
        out += template[last..<range.lowerBound] + value
        last = range.upperBound
    }
    return out + template[last...]
}
/// read: no value, no expected question. text/option: a non-empty one-line answer and the exact question it answers.
func chatJS(_ jobId:String, _ mode:String, _ value:String, _ expected:String?) -> String? {
    guard validJobID(jobId), let m = jsLiteral(mode) else { return nil }
    switch mode {
    case "read":
        guard value.isEmpty, expected == nil else { return nil }
        return fill(chatTemplate, ["JOB_ID":jobId, "MODE_VALUE":m, "VALUE_VALUE":"\"\"", "EXPECTED_VALUE":"null"])
    case "text", "option":
        guard validAnswer(value), let expected, validQuestion(expected), let v = jsLiteral(value), let e = jsLiteral(expected) else { return nil }
        return fill(chatTemplate, ["JOB_ID":jobId, "MODE_VALUE":m, "VALUE_VALUE":v, "EXPECTED_VALUE":e])
    default:
        return nil
    }
}
func validJobID(_ id:String) -> Bool { id.range(of:"^[0-9]{8,16}$", options:.regularExpression) != nil }
func clickJS(_ jobId:String) -> String? { validJobID(jobId) ? clickTemplate.replacingOccurrences(of:"JOB_ID", with:jobId) : nil }
// Job cards on a Naukri list page (recommended jobs, search results). Read only.
let listJS = """
(() => {
  const t = s => (s || '').replace(/\\s+/g, ' ').trim();
  const seen = new Set(); const jobs = [];
  for (const a of document.querySelectorAll('a[href*="/job-listings-"]')) {
    const url = a.href.split('?')[0].split('#')[0];
    if (seen.has(url)) continue; seen.add(url);
    const card = a.closest('article, [class*="jobTuple"], [class*="srp-jobtuple"], [class*="tuple"], li') || a.parentElement;
    const q = s => { const e = card && card.querySelector(s); return e ? t(e.innerText) : ''; };
    jobs.push({url, title: t(a.innerText || a.title).slice(0, 200), company: q('[class*="comp-name"], [class*="companyInfo"] a, [class*="subTitle"]').slice(0, 200),
      location: q('[class*="loc"]').slice(0, 120), experience: q('[class*="exp"]').slice(0, 60), salary: q('[class*="sal"]').slice(0, 60)});
    if (jobs.length >= 40) break;
  }
  const loggedOut = !!document.querySelector('#login_Layer, a[href*="nlogin/login"]') && !document.querySelector('[class*="nI-gNb-drawer__icon"], [class*="user-name"]');
  return JSON.stringify({url: location.href, ready: document.readyState, loggedOut, jobs});
})()
"""
let scripts = ["facts": factsJS, "list": listJS]

if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--self-test" {
    emit(["ok": validURL("https://www.naukri.com/job-listings-react-developer-acme-bengaluru-3-to-5-years-181125000123") && validURL("https://www.naukri.com/mnjuser/recommendedjobs")
          && !validURL("https://evil.com/naukri.com/") && !validURL("https://www.naukri.com.evil.com/x") && !validURL("http://www.naukri.com/x")
          && !validURL("https://www.naukri.com/x\" & do shell script \"y") && scripts.count == 2
          && validJobID("181125000123") && !validJobID("1234567") && !validJobID("12345678901234567") && !validJobID("1811'); alert(1);//")
          && clickJS("181125000123")?.contains("here !== '181125000123'") == true && clickJS("x") == nil && !clickTemplate.contains("\\(")
          // Recruiter answers: read takes no value or expected question; text/option need both; fill is one pass.
          && chatJS("181125000123", "read", "", nil)?.contains("EXPECTED = null") == true
          && chatJS("181125000123", "read", "", "Q?") == nil && chatJS("181125000123", "read", "x", nil) == nil
          && chatJS("181125000123", "text", "0", nil) == nil && chatJS("181125000123", "text", "", "Q?") == nil
          && chatJS("181125000123", "text", "a\nb", "Q?") == nil && chatJS("181125000123", "option", "Yes", "") == nil
          && chatJS("181125000123", "option", "Yes", String(repeating:"Q", count:401)) == nil && chatJS("181125000123", "save", "Yes", "Q?") == nil
          && chatJS("1811", "text", "0", "Q?") == nil
          && chatJS("181125000123", "text", "v VALUE_VALUE", "Q JOB_ID EXPECTED_VALUE?")?.contains("EXPECTED = \"Q JOB_ID EXPECTED_VALUE?\"") == true
          && chatJS("181125000123", "text", "v VALUE_VALUE", "Q JOB_ID EXPECTED_VALUE?")?.contains("VALUE = \"v VALUE_VALUE\"") == true
          && chatJS("181125000123", "text", "\"); alert(1); (\"", "Q?")?.contains("VALUE = \"\\\"); alert(1); (\\\"\"") == true])
}

func becomeResponsibleForSelf() {
    let marker = "JUNE_BROWSER_SELF_RESPONSIBLE"
    if getenv(marker) != nil { return }
    typealias Disclaim = @convention(c) (UnsafeMutablePointer<posix_spawnattr_t?>, Int32) -> Int32
    guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "responsibility_spawnattrs_setdisclaim"),
          let path = Bundle.main.executablePath else { return }
    var attributes: posix_spawnattr_t? = nil
    guard posix_spawnattr_init(&attributes) == 0 else { return }
    defer { posix_spawnattr_destroy(&attributes) }
    guard posix_spawnattr_setflags(&attributes, Int16(POSIX_SPAWN_SETEXEC)) == 0,
          unsafeBitCast(symbol, to: Disclaim.self)(&attributes, 1) == 0 else { return }
    setenv(marker, "1", 1)
    var arguments: [UnsafeMutablePointer<CChar>?] = CommandLine.arguments.map { strdup($0) } + [nil]
    var pid: pid_t = 0
    _ = posix_spawn(&pid, path, nil, &attributes, &arguments, environ)
    unsetenv(marker)
    arguments.forEach { free($0) }
}
becomeResponsibleForSelf()

let source = """
on openTab(u)
    tell application "Google Chrome"
        if (count of windows) is 0 then make new window
        set t to make new tab at end of tabs of front window with properties {URL:u}
        return id of t
    end tell
end openTab

on runPage(tid, js)
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if ((id of t) as text) is tid then return (execute t javascript js)
            end repeat
        end repeat
    end tell
    error number -1728
end runPage

on closeTab(tid)
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if ((id of t) as text) is tid then
                    close t
                    return "closed"
                end if
            end repeat
        end repeat
    end tell
    error number -1728
end closeTab

on chromeStatus()
    tell application "Google Chrome" to return count of windows
end chromeStatus
"""

func call(_ handler:String, _ args:[NSAppleEventDescriptor]) -> NSAppleEventDescriptor {
    var error:NSDictionary?
    guard let script = NSAppleScript(source:source), script.compileAndReturnError(&error) else { emit(["ok":false,"code":"browser-unavailable"]) }
    let event = NSAppleEventDescriptor(eventClass:fourCC("ascr"), eventID:fourCC("psbr"), targetDescriptor:NSAppleEventDescriptor.null(),
                                       returnID:AEReturnID(kAutoGenerateReturnID), transactionID:AETransactionID(kAnyTransactionID))
    event.setParam(NSAppleEventDescriptor(string:handler.lowercased()), forKeyword:fourCC("snam"))
    let list = NSAppleEventDescriptor.list()
    for (i, a) in args.enumerated() { list.insert(a, at:i + 1) }
    event.setParam(list, forKeyword:fourCC("----"))
    let result = script.executeAppleEvent(event, error:&error)
    if let error = error {
        let code = (error[NSAppleScript.errorNumber] as? NSNumber)?.intValue ?? 0
        let message = (error[NSAppleScript.errorMessage] as? String) ?? ""
        let kind = code == -1743 ? "automation-permission" : code == -1728 ? "tab-missing"
            : message.range(of:"JavaScript", options:.caseInsensitive) != nil ? "javascript-off" : "browser-unavailable"
        emit(["ok":false, "code":kind, "number":code, "detail":String(message.prefix(200))])
    }
    return result
}

guard CommandLine.arguments.count == 1,
      let bytes = try? FileHandle.standardInput.read(upToCount:4097), bytes.count <= 4096,
      let input = (try? JSONSerialization.jsonObject(with:bytes)) as? [String:Any],
      let operation = input["operation"] as? String else { emit(["ok":false]) }
let keys = Set(input.keys)

switch operation {
case "status" where keys == ["operation"]:
    emit(["ok":true, "windows":Int(call("chromeStatus", []).int32Value)])
case "open" where keys == ["operation","url"]:
    guard let url = input["url"] as? String, validURL(url) else { emit(["ok":false]) }
    emit(["ok":true, "tab":Int(call("openTab", [NSAppleEventDescriptor(string:url)]).int32Value)])
case "click-apply":
    // The reviewed job id travels with the click; a request without it (or from an older caller) is refused.
    guard keys == ["operation","tab","jobId"], let tab = input["tab"] as? Int, tab > 0, let jobId = input["jobId"] as? String, let js = clickJS(jobId) else { emit(["ok":false]) }
    let text = call("runPage", [NSAppleEventDescriptor(string:String(tab)), NSAppleEventDescriptor(string:js)]).stringValue ?? ""
    guard text.count <= 2000, let data = text.data(using:.utf8), let page = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else {
        emit(["ok":false, "code":"page-unreadable"])
    }
    emit(["ok":true, "page":page])
case "chat":
    // Read or answer Naukri's recruiter questions for the reviewed job only.
    // read: exactly {operation, tab, jobId, mode, value}. text/option: the same plus expectedQuestion. Anything else is refused.
    let readKeys: Set<String> = ["operation","tab","jobId","mode","value"]
    guard keys == readKeys || keys == readKeys.union(["expectedQuestion"]), let tab = input["tab"] as? Int, tab > 0, let jobId = input["jobId"] as? String,
          let mode = input["mode"] as? String, let value = input["value"] as? String else { emit(["ok":false]) }
    let expected: String?
    if keys.contains("expectedQuestion") { guard let e = input["expectedQuestion"] as? String else { emit(["ok":false]) }; expected = e } else { expected = nil }
    guard let js = chatJS(jobId, mode, value, expected) else { emit(["ok":false]) }
    let text = call("runPage", [NSAppleEventDescriptor(string:String(tab)), NSAppleEventDescriptor(string:js)]).stringValue ?? ""
    guard text.count <= 20000, let data = text.data(using:.utf8), let page = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else {
        emit(["ok":false, "code":"page-unreadable"])
    }
    emit(["ok":true, "page":page])
case "facts", "list":
    guard keys == ["operation","tab"], let tab = input["tab"] as? Int, tab > 0, let js = scripts[operation] else { emit(["ok":false]) }
    let text = call("runPage", [NSAppleEventDescriptor(string:String(tab)), NSAppleEventDescriptor(string:js)]).stringValue ?? ""
    guard text.count <= 200000, let data = text.data(using:.utf8), let page = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any] else {
        emit(["ok":false, "code":"page-unreadable"])
    }
    emit(["ok":true, "page":page])
case "close" where keys == ["operation","tab"]:
    guard let tab = input["tab"] as? Int, tab > 0 else { emit(["ok":false]) }
    _ = call("closeTab", [NSAppleEventDescriptor(string:String(tab))])
    emit(["ok":true])
default:
    emit(["ok":false])
}
