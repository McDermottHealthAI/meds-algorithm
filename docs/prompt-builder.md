# Implementation prompt builder

Prepare instructions for Claude or another coding agent. Choose paper/code sources, a **new local or
GitHub repository**, and automatic or explicit profile selection. Evaluation tasks, if supplied, must
already have **labels and task configs**. This form assembles text locally; it does not read your files,
contact GitHub, upload inputs or run an agent.

The generated prompt uses the same maintained instructions as the [static workflow prompt](implementation-prompt.md).
You can edit the result before copying. Demo and full-data execution retain their human review gates.

<div class="prompt-builder" data-prompt-builder>
<!-- prompt-template -->
<noscript>Enable JavaScript to use the builder, or fill in the static workflow prompt.</noscript>
<form data-builder-form>
<fieldset>
<legend>1. Sources</legend>
<label>Available source material
<select name="source_kind"><option value="both">Paper and code/repository</option><option value="paper">Paper only</option><option value="code">Code/repository only</option></select>
</label>
<div data-section="papers">
<label>Paper references <span class="pb-hint">One or more URLs or local paths; include supplementary material and versions.</span>
<textarea name="papers" rows="3" required placeholder="Paper URL or path"></textarea></label>
</div>
<div data-section="code">
<label>Code references <span class="pb-hint">Repository URLs or local paths, commit/tag, relevant configs and checkpoints.</span>
<textarea name="code" rows="3" required placeholder="Repository URL or path, with revision"></textarea></label>
</div>
</fieldset>
<fieldset>
<legend>2. New repository</legend>
<label>Destination
<select name="destination_kind"><option value="local">New local repository</option><option value="github">New GitHub repository</option></select></label>
<div data-section="github" hidden>
<label>GitHub repository <span class="pb-hint">A new owner/name or https://github.com/owner/name.</span>
<input name="github_repo" placeholder="owner/my-algorithm"></label>
<label>Visibility <select name="visibility"><option value="private">Private</option><option value="public">Public</option></select></label>
</div>
<label>New local repository path <span class="pb-hint">Also required for a GitHub destination: this is the agent's working checkout. Choose a directory that does not exist yet.</span>
<input name="local_path" required placeholder="/work/my-algorithm or C:\work\my-algorithm"></label>
</fieldset>
<fieldset>
<legend>3. Profiles</legend>
<label>How should profiles be chosen?
<select name="profile_mode"><option value="automatic">Automatically from source evidence</option><option value="manual">I will select one or more</option></select></label>
<p class="pb-hint">Automatic selection happens in the implementation agent, before generation. It may select several profiles when the sources support them.</p>
<div data-section="profiles" hidden>
<label class="pb-check"><input type="checkbox" name="profiles" value="supervised"> supervised — task-specific learning</label>
<label class="pb-check"><input type="checkbox" name="profiles" value="finetune"> finetune — update pretrained representations</label>
<label class="pb-check"><input type="checkbox" name="profiles" value="probe"> probe — train a head on frozen representations</label>
<label class="pb-check"><input type="checkbox" name="profiles" value="zero_shot_direct"> zero_shot_direct — query the algorithm for a task</label>
<label class="pb-check"><input type="checkbox" name="profiles" value="zero_shot_materialized"> zero_shot_materialized — evaluate generated futures</label>
<label class="pb-check"><input type="checkbox" name="profiles" value="predict_only"> predict_only — apply a fixed algorithm or in-context learner</label>
</div>
</fieldset>
<fieldset>
<legend>4. Dataset and prepared tasks</legend>
<label>Dataset context <span class="pb-hint">Name, revision and MEDS directory. Required when supplying tasks; otherwise optional.</span>
<textarea name="dataset" rows="2" placeholder="Dataset name and revision; MEDS directory"></textarea></label>
<label>Evaluation task inputs
<select name="tasks_mode"><option value="none">Not supplied yet — defer evaluation</option><option value="ready">Prepared bundle — labels and task configs are ready</option></select></label>
<div data-section="tasks" hidden>
<label>Labels location <span class="pb-hint">Label files/directories, including task identities, splits and prediction keys.</span>
<input name="labels_path" placeholder="/data/tasks/labels"></label>
<label>Task configs location <span class="pb-hint">Executable task definitions; zero-shot profiles need ACES criteria and matching predicates.</span>
<input name="configs_path" placeholder="/data/tasks/configs"></label>
<label>Bundle revision or identifier <input name="bundle_revision" placeholder="task-bundle-v1 or immutable revision"></label>
<label>Task subset (optional) <span class="pb-hint">Existing task identifiers only. Leave blank to use all supplied tasks.</span>
<input name="task_subset" placeholder="mortality_30d, readmission_30d"></label>
</div>
<p class="pb-hint">The prompt does not ask the agent to invent tasks or extract labels. Missing or inconsistent inputs defer only the dependent evaluation.</p>
</fieldset>
<fieldset>
<legend>5. Scope and constraints</legend>
<label>Requested endpoint
<select name="scope"><option value="local">Implementation and local tests</option><option value="integration">Also run MEDS-DEV integration</option><option value="full">Prepare for demo and full-data evaluation</option></select></label>
<p class="pb-hint">Preparing for full evaluation does not authorize a demo, dataset download or cluster run. The existing review gates still apply.</p>
<label class="pb-check"><input type="checkbox" name="exploratory_mode" aria-describedby="exploratory-mode-help"> Exploratory mode — allow provisional scientific assumptions</label>
<p class="pb-hint" id="exploratory-mode-help">Off by default. The agent normally asks before implementing a major unresolved scientific choice, such as unspecified feature construction; routine defaults may proceed with documentation. When enabled, provisional design choices must be recorded and reviewed before claiming faithful reproduction. Leakage, cohort/target definitions, evaluation validity and execution approvals still require resolution.</p>
<label>Additional constraints (optional) <span class="pb-hint">For example: algorithm name, hardware limits, checkpoint requirements or implementation priorities.</span>
<textarea name="constraints" rows="3"></textarea></label>
</fieldset>
<div class="pb-actions"><button type="submit" data-generate disabled>Generate prompt</button><button type="button" data-reset disabled>Reset</button></div>
</form>
<p class="pb-status" data-status role="status" aria-live="polite">Fill in the inputs, then generate your prompt.</p>
<label class="pb-output-label">Editable implementation prompt
<textarea data-prompt-output rows="24" spellcheck="false" readonly placeholder="Your prompt will appear here."></textarea></label>
<div class="pb-actions"><button type="button" data-copy disabled>Copy prompt</button><button type="button" data-download disabled>Download .txt</button></div>
</div>
