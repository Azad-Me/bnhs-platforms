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
| 3 | Load volumes, issues, and page counts | `GET /api/volumes` | **Partial** | Implemented and authenticated. Returns volume records, nested issue records, and each issue's page count. It does not return the progress counts/percentages shown by the dashboard. |
| 4 | Overall dashboard totals and progress | Extend `GET /api/volumes` (preferred) or add `GET /api/journals/progress`. Return total volumes/issues/pages and completed, in-review, and unverified page counts, plus the overall percentage. | **Not started** | The screen needs values such as “2,917 of 24,596 pages completed” and 11.9%. No aggregate progress endpoint or response fields were found. |
| 5 | Per-volume and per-issue progress | Include page-status counts and completion percentages for each volume and issue in the volume response (or expose a dedicated progress endpoint). | **Not started** | Needed for the volume percentages, issue progress bars, and the completed/in-review/unverified color segments. Existing issue records only include total page counts. |
| 6 | Hide completed volumes/issues | Support optional query parameters on the catalog endpoint, e.g. `hide_completed_volumes=true` and `hide_completed_issues=true`, or return consistent status/progress fields so the client can filter locally. | **Not started** | The screen has both controls. Client-side filtering is sufficient only if the response includes progress for every returned volume and issue. |
| 7 | Open an issue's page list | `GET /api/volumes/{volume_id}/issues/{issue_id}/pages` | **Completed** | Authenticated route exists, verifies that the issue belongs to the volume, and returns its pages ordered by page number. |
| 8 | Open an issue's page list without volume context | `GET /api/issues/{issue_id}/pages` | **Completed** | An alternate authenticated route exists and returns pages ordered by page number. The nested route is preferable when navigation starts from a volume card. |
| 9 | Show issue page-status totals | Extend the page-list response or add an issue summary response with counts for Unverified, Review, and Completed pages. | **Partial** | The issue detail screen displays these counts. Existing page records expose a raw `status`, but the API does not provide categorized totals or define their mapping. |
| 10 | Claim an unverified page before editing | Add an authenticated claim/assignment operation, e.g. `POST /api/pages/{page_id}/claim`, that atomically claims an eligible page and returns the claim/lock state. | **Not started** | The screen says opening an unverified page claims it so nobody else can edit it. Assignment and lock fields exist in the data model, but no assignment/claim route was found. |
| 11 | Load page QC content and scan | Add an authenticated page-detail operation for read-only OCR text, editable corrected text, nullable current revision before first save, page status, and claim state; provide an authorized page-scan URL/resource for the viewer. | **Not started** | For first-time QC, initialize corrected text from OCR when available, otherwise return an empty editable value. The prototype showed no OCR text for page 6, and the scan failed to load with HTTP 403. |
| 12 | Save draft corrections and view role-scoped history | Add authenticated draft/revision write and history-read operations, with conflict handling, claim checks, and role-based visibility. | **Not started** | First save creates the first user-authored revision based on the OCR baseline when available, otherwise with no parent. QC users see their own revisions/history plus the read-only OCR baseline; reviewers and auditors see the shared page history. Reviewer/auditor screens have not yet been inspected. |
| 13 | Submit review and complete/approve a page | Add workflow operations for submitting a page for review and recording a reviewer decision/approval; define allowed transitions and role checks. | **Not started** | QC submission removes the page from the QC user's queue and makes it visible to reviewers and auditors. The reviewer design shows “Send back” and “Commit & publish”; their exact side effects still need confirmation. |
| 14 | Release or expire page claims | Add an operation to release an assignment when editing is abandoned/completed, and enforce lock expiry when another user attempts to claim. | **Not started** | The assignment model has `lock_expires_at`, but no claim lifecycle or release API was found. |
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

The current `Page.status` is a free-form string. Replace/validate it with a
shared enum so API transitions, queue filtering, and dashboard progress use
the same values. Proposed minimum:

```python
class QCState(str, Enum):
    UNVERIFIED = "unverified"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    NEEDS_CHANGES = "needs_changes"
    COMPLETED = "completed"
```

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
| Dashboard progress | Extend `GET /api/volumes` or add `GET /api/journals/progress` | Return total volume/issue/page counts and completed, in-review, and unverified counts and percentages, including per-volume and per-issue values. First define the canonical mapping from stored page/review state to these categories. |
| Hide completed catalog items | Optional filters on the catalog endpoint, or client filtering | Support the dashboard's hide-completed volume and issue controls using consistent progress fields. |
| Issue page-status totals | Extend `GET /api/volumes/{volume_id}/issues/{issue_id}/pages` or add an issue summary response | Return categorized Unverified, Review, and Completed page counts. |
| Claim page | `POST /api/pages/{page_id}/claim` | Atomically claim an eligible unverified page and return the claim/lock state; reject another active claimant. |
| Load QC page and scan | `GET /api/pages/{page_id}` plus an authorized scan URL/resource | Return OCR text, editable corrected text, revision ID, page status, and claim state; make the page scan available only to authorized users. Resolve the observed prototype 403. |
| Save draft / revision | Authenticated revision write operation | Save corrected text against a base revision, require a valid claim, and detect concurrent edits. |
| Revision history and comparison | `GET /api/pages/{page_id}/revisions` and revision content/diff retrieval | Scope results by role: QC users receive only their own revisions/history; reviewers and auditors receive the common authorized page history, including author/time/source and comparison data. Enforce page access on both list and content retrieval. Reviewer/auditor screen requirements remain to be confirmed. |
| Submit a page for review | `POST /api/pages/{page_id}/submit-review` | Validate the QC user's claim and draft, transition the page to `IN_REVIEW`, record the submitted revision/actor/time, release the QC claim, remove it from QC queues, and make it available in reviewer/auditor views. |
| Reviewer/Admin decision | Authenticated review-decision operation, e.g. send back or commit/publish | Support the visible actions for authorized reviewers and admins; record decision/actor/time and enforce role-based transitions. The Admin prototype exposes “Send back” and “Commit & publish”; exact state transitions, publication effects, and required rationale need product confirmation. |
| Release/expire claim | Authenticated claim release operation plus expiry enforcement | Release a claim when work ends or is abandoned and prevent stale locks from blocking other users. |

## Progress response fields to agree on

Before implementing items 4–6, define exactly how a page maps to the dashboard's
three categories. The current model has a free-form `Page.status` and
`current_approved_revision_id`, but the repository does not define the
`completed`, `in_review`, and `unverified` mapping. Avoid deriving displayed
percentages from ambiguous or inconsistent status rules.

A useful response shape for `GET /api/volumes` would include:

```json
{
  "summary": {
    "volume_count": 100,
    "issue_count": 400,
    "page_count": 24596,
    "completed_page_count": 2917,
    "in_review_page_count": 0,
    "unverified_page_count": 21679,
    "completion_percent": 11.9
  },
  "volumes": [
    {
      "id": 1000,
      "volume_code": "1",
      "page_count": 260,
      "completed_page_count": 195,
      "in_review_page_count": 0,
      "unverified_page_count": 65,
      "completion_percent": 75.0,
      "issues": [
        {
          "id": 1001,
          "issue_code": "1",
          "page_count": 65,
          "completed_page_count": 3,
          "in_review_page_count": 1,
          "unverified_page_count": 61,
          "completion_percent": 5.0
        }
      ]
    }
  ]
}
```

The numbers above illustrate the shape only; except for the dashboard-wide
totals shown in the prototype, they are not a specification of production data.
Percentages should be calculated from integer counts and documented rounding.
The response should include empty volumes/issues where appropriate so the
dashboard can display the complete catalog.

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
