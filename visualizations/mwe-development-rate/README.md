# MWE development rate

A measurement of the working corpus over eleven months ending 2026-07-31: words
written, posts published, and AI tokens logged, each month set against its own
base month.

This folder is a public surface. It is not the corpus, the archive, the registry,
or a complete account of the work.

## Files

    monthly_development_rate.csv  the monthly figures
    summary.json                  the rebuild's own totals and dating tiers

## How the CSV says nothing was measured

A zero and an absence are different claims, and the file keeps them apart. **An
empty cell is never a zero.** It means no value exists for that month, and two
columns say which kind of absence it is.

    posts_coverage   measured        the export covers this month
                     not_in_export   outside the Medium export window
    ai_coverage      measured        a token figure was logged
                     not_logged      nothing was logged for this month

So 2025-09 reads `posts=0` with `posts_coverage=measured` - the export covers it
and it contains no posts, which is a measurement. 2026-07 reads `posts=` with
`posts_coverage=not_in_export` - the Medium index was exported 2026-07-07 and
cannot contain anything published after that date, so there is no measurement to
report. The first eight months read `ai_total=` with `ai_coverage=not_logged`.

An earlier version of this file wrote `0` in all three cases. It was corrected
before publication: for anyone reading the CSV on its own, `0` says
measured-and-zero, which is the one thing two of those months do not say.

## Fields transcribed rather than computed

`summary.json` carries five fields that the two files here cannot derive:
`medium_export_date`, `ai_logging_first_record`, `week_tag_absent_from`,
`week_tagged_files_seen` and `week_tagged_discarded_by_filter_first`. They were
recorded by the 2026-08-02 rebuild run that produced this dataset and are
transcribed, not recomputed. The `provenance` field in that file says so.

They are here because the page quotes them. A figure quoted on a page whose whole
claim is that the reader need not take anything on trust should have a shipped
source, even one that names itself as a transcription.

This folder holds figures, not a rendering of them. The page that draws them is
on the website, under Artistic Research, and it pins its evidence to this folder
at a fixed commit.

The figures live here rather than beside that page because the website's own
indexing contract allows public source links to one repository only, this one,
and its governance page states the rule in words: website-repository files are
referred to by visible path, without a GitHub URL. Committing the data here is
what lets the page's evidence be a link a reader can follow rather than a path
they have to take on trust.

That page carries its charts as pre-rendered inline SVG, so nothing on the
website reads these files at runtime and there is no second copy to drift.

## What the figures are

    words written        1,680,982   across 1,660 documents, deduplicated
    posts published            192   Medium, by its own publication dates
    AI tokens        1,815,940,311   logged period only, beginning 2026-05-24
    months                      11   2025-09 to 2026-07

The written and published series are each indexed to their own 2025-10 value.
They are never summed, and the token panel is not indexed at all.

## What the figures are not

**"Rate" means quantity per month, not rate of change.** Month-over-month growth
is computed nowhere here, and it does not have the same shape: the written index
peaks in 2026-06, while the largest month-over-month rise is 2026-03.

**None of the three series is a productivity measure.** Words written, posts
published and tokens spent are counts of artefacts and of machine work. They do
not measure quality, difficulty, or how much of the work was thinking rather than
typing.

**Two absences on the page are different things.** 2025-09 published is a measured
zero. 2026-07 published is a coverage boundary: the Medium index was exported
2026-07-07 and cannot contain anything published after that date. Neither is
plotted as a point.

**Tokens record what was logged, not what was used.** Nothing is logged before
2026-05-24. That is an absence in the record, not a measured zero, and the page
shades it rather than drawing it at the floor.

## Provenance of the dating

Documents are dated by a three-tier rule settled 2026-07-29: an ISO week tag in
the document's own front matter first; otherwise a modification time that does not
fall inside a known bulk filesystem operation; otherwise the document is dropped.

    835   dated by their own week tag
    830   fall back to modification time
    ---
    1,665 carry a usable date
       -4 fall after the 2026-07-31 cut-off
       -1 dated before 2025-09, where the table begins
    ---
    1,660 shown

No document dated 2026-07 or later carries a week tag, so the right-hand end of
the written series rests on the weaker source and should be read with less
confidence than the left.

One figure quoted on the page cannot be checked from this folder: the rebuild
narrative states that 772 of 1,677 tagged files were discarded by an earlier
ordering. Those two counts come from the 2026-08-02 rebuild run and are not
exported here.

## What checkability does and does not establish

These files contain these figures. That the figures can be checked does not
establish that they are true of the corpus, and this folder does not ask to be
believed beyond what the files show.
