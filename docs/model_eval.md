# Local model evaluation (synthetic practice notes)

**Decision:** keep `qwen3:4b` as the default. Both models scored the same on these notes, so there is no evidence yet that the smaller one is as reliable on harder dictations. `qwen3:1.7b` is about 3 times faster and can be selected with `LLM_MODEL=qwen3:1.7b`.

**Caution:** these 4 notes were also used to tune the rules, so the scores are optimistic. Re-run on real dentist notes when available.

## qwen3:4b

Model `qwen3:4b`: item recall 100%, extra items 0.

| Note | Items found | Missing | Extra | Questions OK | Total € | Diff € | Time s |
|---|---|---|---|---|---|---|---|
| note_01 | 5/5 | – | – | yes | 975.76 | 0.00 | 18 |
| note_02 | 6/6 | – | – | yes | 214.44 | 0.00 | 37 |
| note_03 | 3/3 | – | – | yes | 184.98 | 0.00 | 19 |
| note_04 | 4/4 | – | – | yes | 345.07 | 0.00 | 17 |

## qwen3:1.7b

Model `qwen3:1.7b`: item recall 100%, extra items 0.

| Note | Items found | Missing | Extra | Questions OK | Total € | Diff € | Time s |
|---|---|---|---|---|---|---|---|
| note_01 | 5/5 | – | – | yes | 975.76 | 0.00 | 15 |
| note_02 | 6/6 | – | – | yes | 214.44 | 0.00 | 10 |
| note_03 | 3/3 | – | – | yes | 184.98 | 0.00 | 6 |
| note_04 | 4/4 | – | – | yes | 345.07 | 0.00 | 4 |

