# Journal QC dashboard API checklist

This checklist maps the Journal QC prototype screens to the backend routes
currently present in the repository. Status reflects the code inspected on
2026-11-07:

- **Completed** — the route and the required behavior for this item exist.
- **Partial** — a related route exists, but it does not yet return all data or
  behavior the screen needs.
- **Not started** — no matching route/behavior was found.

The dashboard displays 100 volumes, 400 issues, page totals, overall progress,
per-volume and per-issue progress, completed/in-review/unverified breakdowns,
and controls to hide completed volumes or issues.

## API module ownership

Routes are organized by product domain under `services/`; each domain keeps
its `api.py`, schemas, and service logic together:

- `services/jbnhs/src/catalog` owns volume, issue, and issue-page listing.
- `services/jbnhs/src/dashboard` owns overall dashboard progress.
- `services/jbnhs/src/assignments` owns page claim and release operations.
- `services/jbnhs/src/qc` owns QC page content, revision, and scan reads.
- `services/user_management` owns authentication, roles, and user management.

New workflow areas should get their own domain module (for example,
`services/publishing`) rather than extending Catalog with unrelated routes.

## Admin Users page API checklist

The design-draft Users page shows a user list with name/email, role selectors,
an add-user form (full name, Google account email, role), and a per-user remove
control. The page was observed under the Admin role.

| Screen need | API / contract | Status | Notes |
|---|---|---|---|
| List provisioned users | `GET /api/users?include_inactive=false&offset=0&limit=100` | **Completed** | Implemented and restricted to active Admin users. Returns user profile, role (`level`), active state, and timestamps. Pagination and optional inactive-user inclusion are supported. |
| Load available roles | `GET /api/roles` | **Completed** | Admin-only endpoint returns the fixed role keys and display names for the user form. |
| Add a user | `POST /api/users` with `{ "name", "email", "level": "<role key>" }` | **Completed** | Validates/normalizes name/email and checks the requested role against the fixed database role catalog. Duplicate email returns conflict. |
| Change a user's role | `PATCH /api/users/{user_id}` with `{ "level": "<role key>" }` | **Completed** | Accepts only one of the fixed role keys; last-active-Admin protection remains. |
| Remove/deactivate a user | `DELETE /api/users/{user_id}` | **Completed** | Implemented as deactivation, preserving history; the final active Admin cannot be deactivated. Confirm the UI's remove icon uses this soft-delete behavior and provide confirmation/feedback. |
| Read a user record | `GET /api/users/{user_id}` | **Completed** | Implemented for Admin; useful for detail/edit flows, though no separate detail view was visible on this page. |
| Add/manage a role without code changes | No runtime role CRUD endpoint | **Not required** | Roles are a fixed set (`admin`, `qc_user`, `publisher`). Changes to role definitions require code/migration updates; API access is enforced by role-specific route dependencies, not a permission catalog. |

All `/api/users` and `/api/roles` operations require an active Admin bearer
token and use the shared API response envelope. The role catalog is seeded
with Admin, QC user, and Publisher. Publisher is the prototype's reviewer/
publisher role. No search/filter control was visible in the inspected design;
user pagination is supported by the list API.

Role access is fixed in the API layer by role-specific dependencies; the role
table contains only role identity/display metadata and has no permission
catalog. Adding or changing a role requires a code and migration change.

## Required API checklist

| # | Screen need | API / proposed contract | Status | Notes |
|---|---|---|---|---|
| 1 | Sign in with Google | `POST /api/auth/login` with `{ "credential": "<Google ID token>" }` | **Completed** | Exchanges a verified Google credential for the API bearer token. Only provisioned, active users can sign in. |
| 2 | Identify the signed-in user | `GET /api/auth/me`, using the access token with HTTP bearer authentication | **Completed** | Returns the current authenticated user's profile. |
| 3 | Load volumes, issues, and page counts | `GET /api/volumes` | **Completed** | Authenticated. Returns nested volume and issue data with page-status counts and completion percentages. |
| 4 | Overall dashboard totals and progress | `GET /api/dashboard/progress` | **Completed** | Returns total volumes/issues/pages, completed/in-review/unverified page counts, and overall completion percentage. |
| 5 | Per-volume and per-issue progress | `GET /api/volumes` and `GET /api/volumes/{volume_id}/issues` | **Completed** | Both levels return total/status page counts and completion percentages. |
| 6 | Hide completed volumes/issues | `GET /api/volumes?hide_completed_volumes=true&hide_completed_issues=true` | **Completed** | Filters fully completed volumes/issues. Empty items (zero pages) are not treated as completed. Progress counts retain totals before filtering completed issues. |
| 7 | Open an issue's page list | `GET /api/volumes/{volume_id}/issues/{issue_id}/pages` | **Completed** | Authenticated route exists, verifies that the issue belongs to the volume, and returns its pages ordered by page number. |
| 8 | Open an issue's page list without volume context | `GET /api/issues/{issue_id}/pages` | **Completed** | An alternate authenticated route exists and returns pages ordered by page number. The nested route is preferable when navigation starts from a volume card. |
| 9 | Show issue page-status totals | `GET /api/volumes/{volume_id}/issues` | **Completed** | Issue summaries include counts for Unverified, Review, and Completed pages; `GET /api/issues/{issue_id}/pages` also returns each page's validated QC state. |
| 10 | Claim an unverified page before editing | `POST /api/pages/{page_id}/claim` | **Completed** | QC users and Admins can claim eligible pages. A row lock serializes claims; another active claimant receives 409. Claims expire after 30 minutes. |
| 11 | Load page QC content and scan | `GET /api/pages/{page_id}` | **Completed** | Returns OCR text, the caller's latest draft for QC users (latest revision for Admin/Publisher), nullable revision ID, state, claim state, and a 5-minute authorized scan URL. First-time corrected text is OCR text or empty. |
| 12 | Save draft corrections and view role-scoped history | `POST /api/pages/{page_id}/revisions` saves structured page data; revision history reads remain future work. | **Partial** | QC users must hold the active page claim and send `base_revision_id` (`null` for the OCR baseline) to detect stale saves. Each save stores an immutable structured JSON revision and parent ID. Existing word boxes are server-owned; new words receive an estimated box and alignment warnings when space is insufficient. |
| 13 | Submit review and complete/approve a page | Add workflow operations for submitting a page for review and recording a reviewer decision/approval; define allowed transitions and role checks. | **Not started** | QC submission removes the page from the QC user's queue and makes it visible to reviewers and auditors. The reviewer design shows “Send back” and “Commit & publish”; their exact side effects still need confirmation. |
| 14 | Release or expire page claims | `DELETE /api/pages/{page_id}/claim` | **Completed** | QC users release their own claim; Admins can release any active claim. Release returns a page without a saved draft to `unverified`, or a page with the claimant's draft to `needs_changes`. Expired locks are reclaimed on the next claim attempt. |
| 15 | Load names and highlighted text | Add `GET /api/pages/{page_id}/names`, returning detected names with type (Species, Person, Reference), review status, confidence, and text offsets/spans for highlighting. | **Not started** | The Names panel shows category/status counts and a Highlighted text view. No name-annotation read API was found. |
| 16 | Review detected names | Add an authenticated operation to accept/update an individual name annotation and a bulk action for “Accept all confident.” | **Not started** | The panel exposes “Accept all confident” and “To check”; no annotation decision APIs were found. Exact per-name actions and confidence threshold need confirmation. |
| 17 | Add a missed name | Add `POST /api/pages/{page_id}/names` accepting the name type and exact printed text, then return the created annotation. | **Not started** | The panel explicitly provides Species/Person/Reference choices and an “Exactly as printed” field. No create-name API was found. |

## Future API and data-model backlog

The following requirements were visible or implied by the dashboard and QC
screens but were not implemented in the backend when inspected. Keep them as
future work; endpoint paths and response shapes below are proposals, not
existing contracts.

### Names panel and annotations

The backend currently has no name-annotation model or API. Add a page/revision
scoped annotation record containing, at minimum:

- page and source revision IDs;
- category (`species`, `person`, or `reference`);
- exact printed text and its start/end offsets in the associated text;
- review state (for example, `needs_review` or `accepted`);
- confidence for machine-detected suggestions, if supplied by the detection
  process;
- creator/reviewer and created/updated timestamps.

Offsets must be defined against a specific text revision and a documented
character-counting convention. Return the source `revision_id` with the names
so clients can avoid highlighting annotations against a different text after
edits. Opening the panel is read-only and must not trigger extraction or
change annotations.

| Future operation | Proposed endpoint | Required behavior |
|---|---|---|
| Load names | `GET /api/pages/{page_id}/names` | Return annotations for the page's text revision, counts by category and review state, offsets for highlighting, confidence where available, and the associated `revision_id`. Return an empty list and zero counts when none exist. |
| Review one name | `PATCH /api/pages/{page_id}/names/{name_id}` | Update an annotation's review state and, where allowed, category/text. Enforce page access and claim/role rules. |
| Accept confident names | `POST /api/pages/{page_id}/names/accept-confident` | Bulk-accept eligible suggestions. Define and document the confidence threshold; report changed/skipped counts. |
| Add a missed name | `POST /api/pages/{page_id}/names` | Create an annotation from category and exact printed text, associated with the current text revision. Define how its text span is selected or whether offsets are optional until placed. |

The screen also has All, Species, People, References, and To check filters,
which can be applied client-side to the names response. The Highlighted text
view uses returned spans and the matching page text.

### QC state enum and submission queue behavior

`Page.status` is validated against a shared enum so API transitions, queue
filtering, and dashboard progress use the same values:

The enum is defined in `services/common/constant/qc_state_enum.py`. The
database migration converts legacy `queued` pages to `unverified` and rejects
any other unknown stored state through a validated check constraint.

`UNVERIFIED` means available to claim; `IN_PROGRESS` means claimed/being
worked on by a QC user; `IN_REVIEW` means submitted and awaiting reviewer
action; `NEEDS_CHANGES` means returned to QC for more work; `COMPLETED` means
approved. The UI can display `IN_REVIEW` as “Review.” Keep role authorization
separate from this state enum.

On successful submission, atomically save/identify the submitted revision,
transition `IN_PROGRESS` to `IN_REVIEW`, record who submitted and when, release
the QC claim, and remove the page from that QC user's actionable queue. The
page must then be visible in reviewer and auditor views, subject to their
authorization; auditors are read-only unless a later requirement says
otherwise. Reviewer approval transitions to `COMPLETED`. A return-for-changes
transition should make the page actionable in QC again as `NEEDS_CHANGES` (or
`IN_PROGRESS` when claimed); confirm the exact return state and notification
behavior when the reviewer screen is inspected.

Validate transitions server-side and reject stale/unauthorized submissions.
Do not treat hiding a row in the client as removal from the QC queue: queue
queries must filter by state and role on the server. Migrate existing status
strings explicitly and reject unknown values rather than silently mapping
them.

### First-time QC when no user revision exists

The page image, OCR output, and corrected revision text are separate resources.
Do not require a user-authored revision to open a page:

- Always return the page scan independently of revision state.
- Return OCR text as the read-only source when available.
- Before the first user save, initialize corrected text from the OCR text so
  the QC user can edit a useful starting copy. If OCR is absent, return an
  empty corrected-text value and allow entry from scratch.
- `GET /api/pages/{page_id}` returns a short-lived presigned scan URL rather
  than exposing a public S3 object. The URL expires after five minutes.
- QC users can read unverified, in-progress, or needs-changes pages unless
  another user's active claim exists; in-review/completed page reads are
  restricted to Admin/Publisher roles. The page read never claims a page;
  call the claim endpoint first to acquire or renew the 30-minute lease.
- OCR text is rendered from the stored JSON `lines[].words[].t` values,
  preserving line breaks. Draft revision objects are JSON with a
  `corrected_text` string; QC reads select only that user's latest revision,
  while Admin/Publisher reads select the latest page revision.
- Return `current_revision: null` until a QC user saves. Do not fabricate a
  user revision merely because the page was opened.
- On the first save, create the first user-authored draft revision and record
  its base as the OCR baseline when available; otherwise its base is null.
  Subsequent saves must use optimistic concurrency against their base revision.
- Keep the OCR baseline immutable and visible as source context in history to
  all authorized roles; it is not a QC user's authored revision and must not
  appear as that user's editable history.

The prototype history labels its initial entry “v0 · OCR import.” If the
backend represents that baseline as a `Revision`, its source/author fields
must distinguish a system import from a human-authored draft. The current
`Revision.saved_by` is non-null, so either provide a dedicated system actor or
model the OCR baseline separately rather than assigning it to the first QC
user.

### Other not-yet-implemented workflow APIs

| Future operation | Proposed endpoint / contract | Required behavior |
|---|---|---|
| Dashboard progress | `GET /api/dashboard/progress` | Implemented: returns total volumes/issues/pages and completed, in-review, and unverified counts and percentages. |
| Hide completed catalog items | `GET /api/volumes?hide_completed_volumes=true&hide_completed_issues=true` | Implemented using the progress fields and shared QC state enum. |
| Issue page-status totals | `GET /api/volumes/{volume_id}/issues` | Implemented in issue summaries. |
| Claim page | `POST /api/pages/{page_id}/claim` and `DELETE /api/pages/{page_id}/claim` | Implemented with an atomic page row lock and 30-minute assignment lease. |
| Load QC page and scan | `GET /api/pages/{page_id}` | Implemented; returns role-scoped current revision, OCR/corrected text and claim state, plus an authorized 5-minute scan URL. |
| Save draft / revision | Authenticated revision write operation | Save corrected text against a base revision, require a valid claim, and detect concurrent edits. |
| Revision history and comparison | `GET /api/pages/{page_id}/revisions` and revision content/diff retrieval | Scope results by role: QC users receive only their own revisions/history; reviewers and auditors receive the common authorized page history, including author/time/source and comparison data. Enforce page access on both list and content retrieval. Reviewer/auditor screen requirements remain to be confirmed. |
| Submit a page for review | `POST /api/pages/{page_id}/submit-review` | Validate the QC user's claim and draft, transition the page to `IN_REVIEW`, record the submitted revision/actor/time, release the QC claim, remove it from QC queues, and make it available in reviewer/auditor views. |
| Reviewer/Admin decision | Authenticated review-decision operation, e.g. send back or commit/publish | Support the visible actions for authorized reviewers and admins; record decision/actor/time and enforce role-based transitions. The Admin prototype exposes “Send back” and “Commit & publish”; exact state transitions, publication effects, and required rationale need product confirmation. |
| Release/expire claim | `DELETE /api/pages/{page_id}/claim` | Implemented. Expired assignment rows are marked expired when a later claim is attempted. |

### Saving structured page revisions

`GET /api/pages/{page_id}` includes `data.document` for structured OCR or
revision documents and `data.current_revision_id` for the QC user's current
base. Load/claim the page before editing. Legacy text-only revisions cannot be
used as a geometry-aware base and return a conflict until a structured revision
exists.

Save with `POST /api/pages/{page_id}/revisions` and a QC-user bearer token:

```json
{
  "base_revision_id": null,
  "document": {
    "page": 12,
    "width": 1664,
    "height": 2676,
    "lines": [
      {
        "id": "l1",
        "b": [210, 340, 1480, 392],
        "words": [
          { "id": "w1", "t": "The", "b": [210, 340, 290, 392] },
          { "id": "w2", "t": "", "b": [] },
          { "id": "w3", "t": "Great", "b": [] }
        ]
      }
    ]
  }
}
```

The response contains the new `id`, `based_on_revision_id`, complete
realigned `document`, and `realignment_warnings`. Existing word boxes are
copied from the base revision, regardless of client-supplied coordinates.
Existing words with empty text and an empty box are stored as deletion
tombstones so their IDs are never reused. New words must have a fresh `wN` ID,
non-empty text, and empty box; their box is estimated from neighboring word
geometry and the line box. The save requires an active QC claim and
`in_progress` page state, rejects stale base IDs with `409`, and extends the
claim lease. Line IDs and line membership are fixed in this first version;
line insertion/deletion and revision-history reads are not implemented.

## Text editing and realignment implementation steps

The volunteer guide requires corrected text to retain page geometry: unchanged
words keep their boxes, while replacement words share the box area of the
words they replace. Implement this with structured, immutable page revisions;
do not save only a flattened `corrected_text` string.

1. **Identify OCR words.** Each line has its existing stable line `id`; each
   word now also has an `id` (`w1`, `w2`, ...) assigned in initial reading
   order within that line. IDs are line-scoped. The words array carries current
   reading order, so clients and services must not sort by ID. Never reuse an
   ID within a line's revision history. Re-running OCR can produce different
   words and IDs, so do not silently replace an OCR baseline referenced by
   saved revisions; add baseline versioning or explicit reconciliation first.
2. **Define the edit payload.** The frontend sends the base revision ID and
   edited line/word data. Unchanged words retain their IDs and boxes. A newly
   added word gets the next unused line-local ID and an empty box; its array
   position states where it belongs. A deleted word and deleted line retain
   their IDs in the incoming edit with an explicit empty-result marker (for
   example, empty text and no box). Finalize the marker's exact JSON shape in
   the save API contract. Treat empty results as edit instructions, not as
   active OCR words; retain prior revisions for history.
3. **Validate edits.** Confirm the page and base revision belong together,
   submitted line/word IDs are unique and valid for that base, text is UTF-8,
   and image coordinates are within the page. Reject stale base revisions as
   conflicts rather than applying edits over newer work.
4. **Realign geometry.** Preserve boxes for unchanged words. Replacements
   inherit the replaced word(s)' combined region, divided among replacement
   words using text-width estimates. For insertions, estimate width from text
   metrics and use the line's neighboring word height/vertical placement.
   Preserve the exact scan; boxes position the searchable text layer, they do
   not alter printed content. Detect overlaps, missing space, and ambiguous
   repeated-word matches; return a visible realignment warning for those
   cases rather than silently claiming precise alignment.
5. **Save a full revision.** Persist the complete structured edited page,
   including line IDs, word IDs, text, boxes, order, and any supported review
   metadata. Link it to the base revision and record author/time. Keep every
   saved revision immutable so history and review comparisons are reproducible.
6. **Verify and integrate.** Cover unchanged words, replacements, insertion at
   line start/middle/end, multiple insertions, deletions, split/merged words,
   repeated words, deleted/blank lines, invalid IDs/boxes, and stale saves.
   Confirm the QC reader and the eventual PDF stitcher consume the same
   structured revision shape before enabling the save API.

## Progress response contracts

The dashboard categories use the shared QC state enum. `completed` counts
`COMPLETED`; `in_review` counts `IN_REVIEW`; `unverified` groups
`UNVERIFIED`, `IN_PROGRESS`, and `NEEDS_CHANGES`. This preserves the dashboard's
three displayed categories while keeping the finer workflow states available
to page and queue APIs. Completion percentages are completed pages divided by
total pages, rounded to one decimal place; empty collections report `0.0`.

A response from `GET /api/dashboard/progress` is:

```json
{
  "code": 1,
  "message": "Success",
  "data": {
    "volume_count": 100,
    "issue_count": 400,
    "page_count": 24596,
    "completed_page_count": 2917,
    "in_review_page_count": 0,
    "unverified_page_count": 21679,
    "completion_percent": 11.9
  }
}
```

`GET /api/volumes` returns the catalog list with the same progress fields on
each volume and issue. The numbers above illustrate the shape only; except for
the dashboard-wide totals shown in the prototype, they are not production
counts. The catalog includes empty volumes/issues unless filtered out by the
hide-completed query parameters.

## Existing implementation notes

- Successful responses use the common `{ "code": 1, "message": "Success",
  "data": ... }` envelope. Protected routes require a bearer token.
- The two page-list endpoints currently return page identity, issue, page
  number, status, check-page flag, approved revision ID, and timestamps.
- The issue catalog response includes optional master-PDF, toned-PDF, and
  manifest S3 keys at the issue level. Page records keep page-image source and
  OCR keys only; they do not carry master- or toned-PDF paths.
- The catalog README says page responses include dimensions and source/OCR S3
  keys, but the current `PageRead` schema does not expose those fields. Reconcile
  the README and schema before relying on those fields in a QC detail view.
- Pagination/search are not shown in the supplied dashboard markup and are not
  prerequisites for its current controls. They may be added if loading the full
  catalog becomes a performance issue.

## QC workflow observed from the issue detail screen

Clicking an issue opens a page list with Unverified, Review, and Completed
counts. The screen says opening an unverified page claims it so another person
cannot edit it. Completed/Review rows were marked unavailable to the current
QC user's role, while unverified pages were offered as openable.

**History visibility requirement (product decision):** QC users should see
only revisions and history they authored. Reviewers and auditors should see
the common page history, subject to page authorization. Apply the same rule to
revision content/comparison endpoints, not just the history list. The
reviewer/auditor screens have not yet been inspected, so their additional
history needs are not yet confirmed.

The page 6 editor was opened with permission; this claimed it to the current
user. It displays read-only OCR text, an editable corrected-text field, a scan
viewer with zoom/Fit/synchronized-scroll controls, “Names” and “History”
controls, and “Save draft” and “Submit for review” actions. The Names panel
shows counts for Species, People, References, and To check; a Highlighted text
view; “Accept all confident”; and a form to add a missed name by type and exact
printed text. History shows versions such as the OCR import and offers version
comparison. The sample had no OCR text, and loading its scan returned HTTP
403, so scan authorization and availability need confirmation. Exact name
review actions, confidence threshold, review decisions, and claim release need
confirmation. No flag-resolution requirement is visible on the screens
examined so far.

### Reviewer issue/page design observed

The shared design draft was inspected while signed in as an **Admin** user, not
a reviewer account. The issue contained a page marked “In review.” Its detail
screen displayed the submitter and last-change time, read-only OCR text,
tracked changes against “v0 (OCR import)” with added/removed counts, a
Tracked/Edit toggle, scan controls, Names, History, and the actions “Send
back” and “Commit & publish.” The History panel listed “v1 · Submitted” with
the submitter and timestamp and “v0 · OCR import,” with a “Revert to this”
control. The Names panel showed All/Species/People/References/To check counts,
“Accept all confident,” extracted entries, reference-author fields, and an
add-name form.

#### Admin-visible requirements

The prototype explicitly says an Admin can open any page. The Admin issue
screen also exposes Text QC and Names views, and the Admin could open pages
regardless of their displayed state (including Completed, In review, and
Unverified). The Admin page editor exposes “Harvest names,” Names, and History;
on the In review page it also exposes tracked changes and the “Send back” and
“Commit & publish” actions. The Names panel includes “Accept all confident,”
filters/counts by name type and To check, extracted name entries (including
reference-author fields), and a form for adding a missed name.

Therefore, the API authorization design must explicitly include Admin access
to cross-state page reads and the observed editorial/review actions, subject
to the final product policy. Enforce this using fixed role-specific API
dependencies and audit state-changing actions.

These are observed Admin controls, not verified action semantics. Neither
“Send back,” “Commit & publish,” “Revert to this,” “Harvest names,” nor a
name-acceptance action was activated. Confirm whether committing publishes the
text, approves the submission, or both; whether send-back requires a reason
and returns the page to the QC queue; what harvesting changes; whether
reverting creates a new revision; and whether names are shared annotations.
The reviewer role may have a different permission set and must be confirmed
when its screen/account is available.
