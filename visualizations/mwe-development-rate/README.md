# MWE development rate

A measurement of the working corpus over eleven months ending 2026-07-31: words
written, posts published, and AI tokens logged, each month set against its own
base month.

This folder is a public surface. It is not the corpus, the archive, the registry,
or a complete account of the work.

## Files

    monthly_development_rate.csv  the monthly figures
    summary.json                  the rebuild's own totals and dating tiers

This folder holds figures, not a rendering of them. The page that draws these
figures is on the website, under Artistic Research, and it pins its evidence to
this folder at a fixed commit. Keeping one rendering rather than two is
deliberate: a second copy here would be free to drift from the one readers see.

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
