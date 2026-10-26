# Report: <role> - <site or task in one line>

**Date:** <YYYY-MM-DD> · **Role:** <architect | content and SEO | designer | builder> · **Engine:** <output of `heron --version`> · **Branch:** <name of the branch with the changes, or "no git">
**Task:** <the human's wording verbatim or close to it>

## 1. What was done

Short, to the point, in the past tense. One line - one action.

- <created N pages in `content/<lang>/`: list of keys>
- <…>

## 2. Files

| File | What changed |
|---|---|
| `content/en/services/roof.md` | created: SEO block, sections `includes`, `how`, `faq` |

## 3. Content debts

The "Not filled" summary from the `heron check` report - verbatim, without cuts. Empty - say so: "No debts".

```
<вставка сводки>
```

## 4. Questions for the human

All questions are in `work/questions.md`. Here only the number and the most important: "<N> questions, of them blocking publication: <list of numbers>".

## 5. Warnings left on purpose

| Warning (as in the report) | Why it is left |
|---|---|
| <text> | <reason: content debt until the client answers / needs a decision by the human> |

## 6. Mismatches between the documentation and the engine

What the documentation promises, what the engine does, where it is described (file and section). No mismatches - "None found". The site does not work around a mismatch.

## 7. Checks

| Command | Exit code | Note |
|---|---|---|
| `heron check . --strict --json` | 0 | <number of warnings, if not `--strict`> |
| `heron build . --env prod --strict` | 0 | builder only |

## 8. What was not done and why

Everything from the task that remains: the reason (no fact, no capability in the engine, stopped by the "three rounds" rule), a link to the question or to the engine task.
