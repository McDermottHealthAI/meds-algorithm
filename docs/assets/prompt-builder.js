/* No network calls or persisted inputs: the documentation embeds the canonical implementation prompt. */
(function () {
  "use strict";
  const profiles = ["supervised", "finetune", "probe", "zero_shot_direct", "zero_shot_materialized", "predict_only"];
  const scopes = {
    local: "Implementation and local tests only.",
    integration: "Implementation, local tests and MEDS-DEV integration; stop before the demo.",
    full: "Implementation, local tests, MEDS-DEV integration and preparation for demo/full-data evaluation; wait for the existing execution approvals."
  };
  const clean = (value) => String(value ?? "").trim();
  function required(value, label) {
    const result = clean(value);
    if (!result) throw new Error(`Supply ${label}.`);
    return result;
  }
  function choice(value, allowed, label) {
    if (!allowed.includes(value)) throw new Error(`Choose a valid ${label}.`);
    return value;
  }
  function renderPrompt(template, values) {
    const source = choice(values.source_kind, ["paper", "code", "both"], "source type");
    const destination = choice(values.destination_kind, ["local", "github"], "destination");
    const mode = choice(values.profile_mode, ["automatic", "manual"], "profile selection");
    const tasks = choice(values.tasks_mode, ["none", "ready"], "task-input option");
    const scope = choice(values.scope, Object.keys(scopes), "work scope");
    if (values.exploratory_mode !== undefined && typeof values.exploratory_mode !== "boolean") {
      throw new Error("Exploratory mode must be an explicit checkbox selection.");
    }
    let repository = "New local Git repository only; do not create a GitHub repository.";
    if (destination === "github") {
      const name = required(values.github_repo, "the new GitHub repository")
        .replace(/^https:\/\/github\.com\//, "").replace(/\/$/, "");
      if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\/[A-Za-z0-9_.-]+$/.test(name)
          || [".", ".."].includes(name.split("/")[1])) {
        throw new Error("Use owner/name or https://github.com/owner/name for the new repository.");
      }
      const visibility = choice(values.visibility, ["private", "public"], "repository visibility");
      repository = `New GitHub repository: https://github.com/${name}; visibility: ${visibility}.`;
    }
    let selection = "automatic";
    if (mode === "manual") {
      const selected = Array.isArray(values.profiles) ? [...new Set(values.profiles)] : [];
      if (!selected.length || selected.some((name) => !profiles.includes(name))) {
        throw new Error("Select at least one supported profile.");
      }
      selection = `Explicit profiles: ${selected.join(", ")}.`;
    }
    let bundle = "Not supplied. Continue implementation and synthetic tests; defer evaluation on external task bundles.";
    if (tasks === "ready") {
      required(values.dataset, "the dataset name, revision and MEDS path for these tasks");
      bundle = [
        `Prepared labels: ${required(values.labels_path, "the prepared labels location")}`,
        `Prepared task configs: ${required(values.configs_path, "the prepared task-config location")}`,
        `Bundle revision/identifier: ${required(values.bundle_revision, "the bundle revision or identifier")}`,
        `Task subset: ${clean(values.task_subset) || "All tasks already present in this bundle."}`
      ].join("\n");
    }
    const replacements = {
      PAPER_REFERENCES_OR_NOT_SUPPLIED: source === "code" ? "Not supplied." : required(values.papers, "at least one paper reference"),
      CODE_REFERENCES_OR_NOT_SUPPLIED: source === "paper" ? "Not supplied." : required(values.code, "at least one code/repository reference"),
      NEW_REPOSITORY_DESTINATION: repository,
      NEW_LOCAL_REPOSITORY_PATH: required(values.local_path, "a new local repository path"),
      PROFILE_SELECTION: selection,
      DATASET_CONTEXT_OR_NOT_SUPPLIED: clean(values.dataset) || "Not supplied; use synthetic data for local implementation tests.",
      PREPARED_TASK_BUNDLE_OR_NOT_SUPPLIED: bundle,
      WORK_SCOPE: scopes[scope],
      SCIENTIFIC_AMBIGUITY_MODE: values.exploratory_mode === true
        ? "Exploratory mode explicitly enabled: provisional algorithm-design assumptions are permitted under the policy below."
        : "Confirmation required (default): ask before implementing material unresolved scientific choices.",
      ADDITIONAL_CONSTRAINTS_OR_NONE: clean(values.constraints) || "None."
    };
    return template.replace(/<([A-Z][A-Z0-9_]*)>/g, (token, key) => {
      if (!Object.hasOwn(replacements, key)) throw new Error(`Unknown prompt field: ${token}`);
      return replacements[key];
    });
  }
  function init(root) {
    if (root.dataset.initialized) return;
    const source = root.querySelector("[data-prompt-template]");
    if (!source) return;
    const template = JSON.parse(source.textContent);
    const form = root.querySelector("[data-builder-form]");
    const output = root.querySelector("[data-prompt-output]");
    const status = root.querySelector("[data-status]");
    const copy = root.querySelector("[data-copy]");
    const download = root.querySelector("[data-download]");
    const generate = root.querySelector("[data-generate]");
    const reset = root.querySelector("[data-reset]");
    root.dataset.initialized = "true";
    let stale = true;
    const field = (name) => form.elements.namedItem(name);
    function section(name, visible, requiredNames = []) {
      const block = root.querySelector(`[data-section="${name}"]`);
      block.hidden = !visible;
      block.querySelectorAll("input, textarea, select").forEach((input) => {
        input.disabled = !visible;
        input.required = visible && requiredNames.includes(input.name);
      });
    }
    function update() {
      section("papers", field("source_kind").value !== "code", ["papers"]);
      section("code", field("source_kind").value !== "paper", ["code"]);
      section("github", field("destination_kind").value === "github", ["github_repo"]);
      section("profiles", field("profile_mode").value === "manual");
      const ready = field("tasks_mode").value === "ready";
      section("tasks", ready, ["labels_path", "configs_path", "bundle_revision"]);
      field("dataset").required = ready;
    }
    form.addEventListener("input", () => {
      update();
      stale = true;
      copy.disabled = download.disabled = true;
      status.textContent = output.value ? "Inputs changed. Generate again to update the prompt; existing edits remain below." : "Fill in the inputs, then generate your prompt.";
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const data = new FormData(form);
      const values = Object.fromEntries(data.entries());
      values.profiles = data.getAll("profiles");
      values.exploratory_mode = field("exploratory_mode").checked;
      try {
        output.value = renderPrompt(template, values);
        output.readOnly = false;
        stale = false;
        copy.disabled = download.disabled = false;
        status.textContent = "Prompt ready. Review or edit it, then copy or download.";
      } catch (error) {
        copy.disabled = download.disabled = true;
        status.textContent = error.message;
      }
    });
    output.addEventListener("input", () => {
      download.disabled = copy.disabled = stale || !output.value.trim();
    });
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(output.value);
        status.textContent = "Prompt copied.";
      } catch (_) {
        output.focus();
        output.select();
        status.textContent = "Clipboard access is unavailable. The prompt is selected; use Ctrl+C or Command+C.";
      }
    });
    download.addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([output.value], {type: "text/plain;charset=utf-8"}));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "meds-algorithm-implementation.txt";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    });
    reset.addEventListener("click", () => {
      form.reset();
      stale = true;
      update();
      output.value = "";
      output.readOnly = true;
      copy.disabled = download.disabled = true;
      status.textContent = "Reset. Fill in the inputs, then generate your prompt.";
    });
    update();
    generate.disabled = reset.disabled = false;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = {renderPrompt, init};
  if (typeof document !== "undefined") {
    const start = () => document.querySelectorAll("[data-prompt-builder]").forEach(init);
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
    if (typeof document$ !== "undefined") document$.subscribe(start);
  }
})();
