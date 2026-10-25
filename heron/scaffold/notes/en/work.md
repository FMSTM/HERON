# agents/work — what the agent hands in

The agent puts its results here: `structure.md` (the site structure, architect),
`questions.md` (questions for a person) and `report.md` (the report) — following
the samples in `agents/templates/`. This is the only part of the kit an agent edits.

The engine does not read this folder: it never reaches the build, the image or
the publication, and `heron init --agents` leaves it alone.
