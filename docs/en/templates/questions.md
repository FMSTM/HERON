# Questions for the human - <site>

**Rule:** everything that is not in the source goes here, not into the site text. The field stays empty until there is an answer. Every question comes with options and a recommendation, so that the human answers with a choice, not with an essay.
**Statuses:** `open` · `answered` (the answer is in the column, the change is made) · `dropped` (not needed, the reason is in the column).

| # | Question | Options | Recommendation and why | Where it is used | Blocks publication | Status / answer |
|---|---|---|---|---|---|---|
| Q1 | Phone for the footer and the markup | - | - (a fact, no options) | `site.yaml` → `contact.phone` | yes | open |
| Q2 | What to do with the "News" section of the old site (12 posts 2019-2021, no traffic) | A: move as `articles/`; B: 410 for the whole prefix `/news/*`; C: 301 to the home page | **B** - the posts are outdated, there is no traffic, a search engine treats a 301 to the home page as a soft 404 | `site.yaml` → `gone` | no | open |

No questions - the table is empty, and under it the line: "No questions: all facts are taken from <source>".
