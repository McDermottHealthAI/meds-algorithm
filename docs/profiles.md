# Choosing profiles

A profile describes an algorithm's lifecycle. A repository may declare several profiles and implement them
in one package. Choose them with Copier's `profiles` multiselect, or supply a data file:

```yaml
profiles: [finetune, probe, zero_shot_direct]
```

The [prompt builder](prompt-builder.md) supports automatic selection from paper/code evidence or an
explicit selection of several profiles before repository generation.

The [canonical lifecycle table](reference/spec.md#3-commands-and-algorithm-profiles) lists the exact steps.

Only preprocessing and pretraining share command names. They may share artifacts when input identities,
configuration, payload format and training scope match. Selecting two profiles does not automatically
make their artifacts compatible.

| Profile | Use when |
|---|---|
| `supervised` | Learning a task-specific algorithm directly from the dataset's training labels. |
| `finetune` | Updating a pretrained encoder together with a task-specific head. |
| `probe` | Fitting a task-specific head on frozen encoder representations. |
| `zero_shot_direct` | Translating an ACES task into direct algorithm queries and decoding probabilities without labels. |
| `zero_shot_materialized` | Generating task-independent futures, then evaluating the task on history plus those futures. |
| `predict_only` | Preprocessing then applying a supplied fixed algorithm or an in-context learner, without a training command. |

`predict_only` is the renamed packaged profile. It does not mean probe training. In-context learners may
read explicitly selected train/tuning examples; fixed scores need no labels. Neither may read evaluated
labels before its probabilities are final.

## Select a profile when running commands

Each invocation selects one of the repository's declared profiles. The executable is named after your
algorithm's slug, with underscores replaced by hyphens: `algorithm_slug: my_algorithm` creates the
command `my-algorithm`. Substitute your own command name below.

From the generated repository's root, with the `probe` profile declared:

```bash
uv sync --extra test

# List the profiles implemented by this repository.
uv run my-algorithm profiles

# List the commands in the probe lifecycle.
uv run my-algorithm commands --profile probe

# Register its descriptor in an existing MEDS-DEV checkout.
uv run meds-algorithm-add-to-meds-dev \
  --meds-dev /path/to/MEDS-DEV --name my-algorithm --profile probe
```

Replace `/path/to/MEDS-DEV` with your checkout. Registration copies
`algorithms/probe/model.yaml` into MEDS-DEV under `my-algorithm__probe`.
Here `--name my-algorithm` chooses the registration name; it does not rename the executable.
For SLURM, select the profile with `PROFILE=probe`; see [Running an algorithm](running.md)
for input paths, dry runs and execution settings.

The probe's `infer_embeddings` stage materializes keyed representations without labels. `train_probe`
fits a head on training representations, and `predict_probe` applies it to explicit evaluated embeddings.
Supervised/fine-tuned prediction instead takes `input_data_dir` and the fitted algorithm. Neither dependency
is assumed to disappear just because training recorded its path.

The [software contract](reference/spec.md#9-software-interfaces) gives every command's arguments, artifact type, label
access, class responsibilities, compatibility checks, and acceptance requirements. See
[migration](migration-v4.md) for an existing repository.
