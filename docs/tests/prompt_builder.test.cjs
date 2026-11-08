const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {test} = require("node:test");
const {JSDOM} = require("jsdom");
const {renderPrompt} = require("../assets/prompt-builder.js");
const root = path.join(__dirname, "../..");
const read = (name) => fs.readFileSync(path.join(root, name), "utf8").replace(/\r\n/g, "\n");
const section = read("docs/implementation-prompt.md");
const template = section.match(/```text\n([\s\S]*?)\n```/)[1];
const base = {
  source_kind: "both", papers: "paper.pdf", code: "https://github.com/example/source @ abc123",
  destination_kind: "local", local_path: "/work/new-algorithm", profile_mode: "automatic",
  tasks_mode: "none", scope: "local", visibility: "private", profiles: ["finetune", "probe"],
  github_repo: "example/new-algorithm", dataset: "Demo dataset v1 at /data/meds",
  labels_path: "/data/tasks/labels", configs_path: "/data/tasks/configs", bundle_revision: "tasks-v1"
};
function browser() {
  const html = read("docs/prompt-builder.md").replace("<!-- prompt-template -->", `<script type="application/json" data-prompt-template>${JSON.stringify(template).replace(/</g, "\\u003c")}</script>`);
  const dom = new JSDOM(html, {url: "https://example.test/docs/prompt-builder/", runScripts: "outside-only"});
  dom.window.eval(read("docs/assets/prompt-builder.js"));
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  const doc = dom.window.document;
  const form = doc.querySelector("form");
  const field = (name) => form.elements.namedItem(name);
  const set = (name, value) => { field(name).value = value; field(name).dispatchEvent(new dom.window.Event("input", {bubbles: true})); };
  const output = doc.querySelector("[data-prompt-output]");
  return {dom, doc, form, field, set, output};
}
test("all source, destination, profile, task, scope and ambiguity modes preserve the shared contract", () => {
  for (const source_kind of ["paper", "code", "both"])
    for (const destination_kind of ["local", "github"])
      for (const profile_mode of ["automatic", "manual"])
        for (const tasks_mode of ["none", "ready"])
          for (const scope of ["local", "integration", "full"])
            for (const exploratory_mode of [false, true]) {
            const prompt = renderPrompt(template, {...base, source_kind, destination_kind, profile_mode, tasks_mode, scope, exploratory_mode});
            assert(!/<[A-Z][A-Z0-9_]*>/.test(prompt));
            assert(prompt.includes("Only after approval, run:"));
            assert(prompt.includes("minimalist, auditable, object-oriented"));
            assert(prompt.includes("Do not generate new tasks,"));
            assert(prompt.includes("In BOTH modes, ambiguities about leakage"));
            assert(prompt.includes("Require review of these decisions before claiming faithful reproduction."));
            assert.equal(prompt.includes("Exploratory mode explicitly enabled:"), exploratory_mode);
            assert.equal(prompt.includes("Confirmation required (default):"), !exploratory_mode);
            assert.equal(prompt.includes("paper.pdf"), source_kind !== "code");
            assert.equal(prompt.includes(base.code), source_kind !== "paper");
            assert.equal(prompt.includes("New GitHub repository:"), destination_kind === "github");
            assert.equal(prompt.includes("Explicit profiles: finetune, probe."), profile_mode === "manual");
            assert.equal(prompt.includes("Prepared labels: /data/tasks/labels"), tasks_mode === "ready");
          }
});
test("omitted ambiguity mode defaults to confirmation and non-boolean opt-ins are rejected", () => {
  assert.equal(renderPrompt(template, base), renderPrompt(template, {...base, exploratory_mode: false}));
  assert(renderPrompt(template, base).includes("Confirmation required (default):"));
  for (const exploratory_mode of ["false", "true", "on", null, 0, 1]) {
    assert.throws(() => renderPrompt(template, {...base, exploratory_mode}), /explicit checkbox/);
  }
});
test("exploratory checkbox is opt-in, invalidates the previous prompt and resets to confirmation", () => {
  const {dom, doc, form, field, set, output} = browser();
  try {
    const checkbox = field("exploratory_mode");
    assert.equal(checkbox.checked, false);
    assert.equal(checkbox.defaultChecked, false);
    assert(doc.getElementById(checkbox.getAttribute("aria-describedby")));
    set("papers", base.papers); set("code", base.code); set("local_path", base.local_path);
    form.requestSubmit();
    assert(output.value.includes("Confirmation required (default):"));
    const original = output.value;
    checkbox.click();
    assert.equal(checkbox.checked, true);
    assert(doc.querySelector("[data-copy]").disabled && doc.querySelector("[data-download]").disabled);
    assert.equal(output.value, original);
    form.requestSubmit();
    assert(output.value.includes("Exploratory mode explicitly enabled:"));
    assert(!output.value.includes("Confirmation required (default):"));
    assert(output.value.includes("Only after approval, run:"));
    checkbox.click();
    form.requestSubmit();
    assert.equal(output.value, original);
    checkbox.click();
    form.requestSubmit();
    doc.querySelector("[data-reset]").click();
    assert.equal(checkbox.checked, false);
    assert.equal(output.value, "");
  } finally { dom.window.close(); }
});
test("incomplete or invalid plans fail instead of yielding an executable-looking prompt", () => {
  for (const bad of [
    {papers: ""}, {code: ""}, {local_path: ""}, {source_kind: "unknown"},
    {profile_mode: "manual", profiles: []}, {profile_mode: "manual", profiles: ["invented"]},
    {destination_kind: "github", github_repo: "https://other.test/owner/repo"},
    {destination_kind: "github", visibility: "internal"},
    {tasks_mode: "ready", dataset: ""}, {tasks_mode: "ready", labels_path: ""},
    {tasks_mode: "ready", configs_path: ""}, {tasks_mode: "ready", bundle_revision: ""}
  ]) assert.throws(() => renderPrompt(template, {...base, ...bad}));
});
test("selected task subsets and literal user text are preserved without recursive substitution", () => {
  const literal = '</textarea><script>window.injected = true</script> <PROFILE_SELECTION> $&';
  const prompt = renderPrompt(template, {...base, tasks_mode: "ready", task_subset: "mortality_30d", constraints: literal});
  assert(prompt.includes("Task subset: mortality_30d"));
  assert(prompt.includes(literal));
  assert(prompt.includes("selects only tasks already present"));
});
test("the form reveals only relevant required fields and renders multiple profiles", () => {
  const {dom, doc, form, field, set, output} = browser();
  try {
    set("source_kind", "code");
    assert(field("papers").disabled);
    assert(!field("papers").required);
    set("code", base.code);
    set("local_path", base.local_path);
    set("destination_kind", "github");
    assert(field("github_repo").required);
    set("github_repo", base.github_repo);
    set("profile_mode", "manual");
    form.requestSubmit();
    assert(doc.querySelector("[data-status]").textContent.includes("Select at least one"));
    for (const name of ["finetune", "probe"]) doc.querySelector(`[value="${name}"]`).checked = true;
    set("tasks_mode", "ready");
    assert(field("dataset").required && field("labels_path").required && field("configs_path").required);
    for (const name of ["dataset", "labels_path", "configs_path", "bundle_revision"]) set(name, base[name]);
    form.requestSubmit();
    assert(output.value.includes("Explicit profiles: finetune, probe."));
    assert(output.value.includes("visibility: private"));
    assert(output.value.includes("Prepared task configs: /data/tasks/configs"));
    assert(!doc.querySelector("[data-copy]").disabled);
    set("tasks_mode", "none");
    assert(field("labels_path").disabled && !field("dataset").required);
    form.requestSubmit();
    assert(!output.value.includes("Prepared labels:"));
  } finally { dom.window.close(); }
});
test("edited output copies and downloads exactly; input changes invalidate it and reset clears it", async () => {
  const {dom, doc, form, set, output} = browser();
  try {
    set("papers", base.papers); set("code", base.code); set("local_path", base.local_path);
    form.requestSubmit();
    const copy = doc.querySelector("[data-copy]");
    const download = doc.querySelector("[data-download]");
    let copied, blob, filename;
    Object.defineProperty(dom.window.navigator, "clipboard", {value: {writeText: async (value) => {copied = value;}}});
    dom.window.URL.createObjectURL = (value) => {blob = value; return "blob:test";};
    dom.window.URL.revokeObjectURL = () => {};
    dom.window.HTMLAnchorElement.prototype.click = function () { filename = this.download; };
    output.value += "\nUser edit.";
    output.dispatchEvent(new dom.window.Event("input", {bubbles: true}));
    copy.click(); await new Promise(setImmediate);
    assert.equal(copied, output.value);
    download.click();
    const downloaded = await new Promise((resolve) => { const reader = new dom.window.FileReader(); reader.onload = () => resolve(reader.result); reader.readAsText(blob); });
    assert.equal(downloaded, output.value);
    assert.equal(filename, "meds-algorithm-implementation.txt");
    const previous = output.value;
    set("constraints", "new constraint");
    assert(copy.disabled && download.disabled);
    assert.equal(output.value, previous);
    form.requestSubmit();
    output.value = ""; output.dispatchEvent(new dom.window.Event("input")); assert(copy.disabled);
    output.value = "Restored edit"; output.dispatchEvent(new dom.window.Event("input")); assert(!copy.disabled);
    doc.querySelector("[data-reset]").click();
    assert.equal(output.value, ""); assert(copy.disabled && output.readOnly);
  } finally { dom.window.close(); }
});
test("clipboard denial provides a selectable fallback without losing edited content", async () => {
  const {dom, doc, form, set, output} = browser();
  try {
    set("papers", base.papers); set("code", base.code); set("local_path", base.local_path);
    form.requestSubmit();
    Object.defineProperty(dom.window.navigator, "clipboard", {value: {writeText: async () => {throw new Error("denied");}}});
    doc.querySelector("[data-copy]").click(); await new Promise(setImmediate);
    assert(doc.querySelector("[data-status]").textContent.includes("Ctrl+C"));
    assert.equal(output.selectionStart, 0); assert.equal(output.selectionEnd, output.value.length);
  } finally { dom.window.close(); }
});
test("HTML-like references remain inert text and repeated initialization preserves edits", () => {
  const {dom, doc, form, set, output} = browser();
  try {
    const hostile = '</textarea><img src=x onerror="window.injected=true">';
    set("papers", hostile); set("code", base.code); set("local_path", base.local_path);
    form.requestSubmit();
    assert(output.value.includes(hostile)); assert.equal(doc.querySelector("img"), null);
    assert.equal(dom.window.injected, undefined);
    output.value = "My edited prompt";
    doc.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
    assert.equal(output.value, "My edited prompt");
  } finally { dom.window.close(); }
});
