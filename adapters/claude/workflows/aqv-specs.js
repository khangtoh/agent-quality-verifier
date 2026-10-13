export const meta = {
  name: 'aqv-specs',
  description: 'Draft requirements from the goal and plan in the form aqv checks, and validate them with aqv',
  whenToUse: 'A goal and a plan exist and .aqv.yml is committed; no requirements are written yet, or the plan grew',
  phases: [
    { title: 'Preflight', detail: 'goal, plan, .aqv.yml and the aqv binary are in place' },
    { title: 'Draft', detail: 'write the spec files and the ID registry from the plan' },
    { title: 'Check', detail: 'aqv check --only T1 on a scratch copy, and a review against the plan' },
  ],
}

// args: { aqv, goal, plan, maxRevisions }. Nothing is committed: the spec is yours to review and commit.
const a = args || {}
const AQV = a.aqv || 'aqv'
const GOAL = a.goal || 'GOAL.md'
const PLAN = a.plan || 'PLAN.md'
const MAX_REVISIONS = a.maxRevisions === undefined ? 1 : a.maxRevisions

const RULES = `
Spec conventions (the verifier parses these exactly):
- One requirement per line: \`- **AC-<area>-<nnn>** (api: METHOD /path): One sentence.\`
  Example: \`- **AC-auth-002** (api: POST /login): Accounts lock after 3 consecutive failed sign-in attempts.\`
- The ID matches ^AC-[a-z0-9]+(?:-[a-z0-9]+)*-\\d{3}$ (lower-case area, three digits).
- \`(api: ...)\` only on requirements an HTTP endpoint serves. The method is upper case and the path starts
  with /. Several operations: \`(api: POST /a, GET /b)\`. No other tags exist.
- Every ID is also a line in the ID registry. An ID in the registry is never reused, even if its
  requirement is gone; new IDs continue the numbering of their area.
- Headings and prose around the requirement lines are fine; only matching lines are read.

What makes a requirement checkable:
- One behaviour someone can observe, stated so a test can fail it. No "should be fast", no "and".
- Small enough for one commit of code and tests (under the max_commit_lines in .aqv.yml, 400 by default),
  because each code commit may cite only one requirement.
- Final wording: changing a requirement later marks its results stale until its code or tests change too.
- Listed in the order they should be built, dependencies first.`

const PRE = {
  type: 'object',
  required: ['ok', 'problems', 'specsGlob', 'registryPath', 'registryIds'],
  properties: {
    ok: { type: 'boolean' },
    problems: { type: 'array', items: { type: 'string' } },
    specsGlob: { type: 'string' },
    registryPath: { type: 'string' },
    registryIds: { type: 'array', items: { type: 'string' } },
  },
}
const DRAFT = {
  type: 'object',
  required: ['files', 'requirements'],
  properties: {
    files: { type: 'array', items: { type: 'string' } },
    requirements: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'text'],
        properties: { id: { type: 'string' }, text: { type: 'string' }, api: { type: 'string' } },
      },
    },
  },
}
const FORMAT = {
  type: 'object',
  required: ['ran', 'verdict', 'problems'],
  properties: {
    ran: { type: 'boolean' },
    verdict: { type: 'string' },
    problems: { type: 'array', items: { type: 'string' } },
  },
}
const REVIEW = {
  type: 'object',
  required: ['uncovered', 'unplanned', 'unclear'],
  properties: {
    uncovered: { type: 'array', items: { type: 'string' } },
    unplanned: { type: 'array', items: { type: 'string' } },
    unclear: { type: 'array', items: { type: 'string' } },
  },
}

phase('Preflight')
const pre = await agent(
  `Check that this repository is ready for requirements to be written. Change nothing.

Report a problem for each of these that does not hold:
- ${GOAL} exists and states a goal.
- ${PLAN} exists and describes what will be built.
- This is a git repository with at least one commit.
- .aqv.yml exists and is committed (git ls-files .aqv.yml).
- \`${AQV}\` runs: with no arguments it prints a usage line that starts "usage: aqv check".

Read .aqv.yml and return its \`specs\` glob (default "specs/*.md") as specsGlob and its \`ids_registry\`
(default "specs/.ids") as registryPath. Return every ID already in the registry file as registryIds
(empty if the file does not exist). ok is true only when there are no problems.`,
  { label: 'preflight', effort: 'low', schema: PRE },
)
if (!pre) return { ready: false, problems: ['The preflight agent did not finish'] }
if (!pre.ok) {
  log(`Not ready: ${pre.problems.join('; ')}`)
  return { ready: false, problems: pre.problems }
}

const draftPrompt = (feedback) => `Write the requirements for this project from ${GOAL} and ${PLAN}.

Write them to a file matching ${pre.specsGlob} (one file per area of the plan) and add every new ID to
${pre.registryPath}, one per line. These IDs are already issued and must not be reused:
${pre.registryIds.join(', ') || '(none)'}.
${RULES}

Cover everything the plan commits to and nothing it does not. Do not write code, tests or the OpenAPI
contract: each operation is added to the contract when its requirement is built. Do not commit, and do
not touch .aqv.yml.
${feedback ? `\nThis is a revision. Keep what was right and fix these:\n${feedback}\n` : ''}
Return the files you wrote and every requirement now in them, in order.`

const check = () =>
  parallel([
    () =>
      agent(
        `Validate the uncommitted spec files with the verifier, on a scratch copy so this repository is
not changed. The verifier reads committed files only, hence the copy.

  tmp=$(mktemp -d)
  git clone -q . "$tmp/repo"
  for f in ${pre.specsGlob} ${pre.registryPath}; do mkdir -p "$tmp/repo/$(dirname "$f")" && cp "$f" "$tmp/repo/$f"; done
  git -C "$tmp/repo" add -A
  git -C "$tmp/repo" -c user.name=draft -c user.email=draft@aqv.local -c commit.gpgsign=false commit -q --allow-empty -m "docs(spec): draft"
  ${AQV} check --repo "$tmp/repo" --only T1 --out "$tmp/out"

Then read "$tmp/out/results.json". Return verdict = its checks.T1, and problems = the summary of every
entry in its results whose verdict is fail or error, copied verbatim and split into one problem per
item. ran is false if any command above failed before the check produced results.json; say which in
problems. Do not edit the spec files.`,
        { label: 'format: aqv T1', phase: 'Check', effort: 'low', schema: FORMAT },
      ),
    () =>
      agent(
        `Review the requirements in ${pre.specsGlob} against ${GOAL} and ${PLAN}. You did not write them;
judge them as the person who must sign them off. Do not edit anything.

Return three lists, each item one sentence naming the requirement ID or the plan item:
- uncovered: something the plan commits to that no requirement states.
- unplanned: a requirement the goal and plan do not ask for.
- unclear: a requirement a test could not fail as worded, or one that states more than one behaviour,
  or one too large for a single commit of code and tests.
An empty list means you looked and found none.`,
        { label: 'review against the plan', phase: 'Check', schema: REVIEW },
      ),
  ])

let draft = null
let format = null
let review = null
let issues = []
for (let round = 0; round <= MAX_REVISIONS; round++) {
  phase('Draft')
  draft = await agent(draftPrompt(issues.join('\n')), {
    label: round ? `revise specs (${round})` : 'draft specs',
    schema: DRAFT,
  })
  if (!draft) return { ready: false, problems: ['The drafting agent did not finish'] }

  phase('Check')
  ;[format, review] = await check()
  issues = []
  if (!format || !format.ran) issues.push(`aqv did not run: ${format ? format.problems.join('; ') : 'no result'}`)
  else if (format.verdict !== 'pass') issues.push(...format.problems.map((p) => `aqv T1: ${p}`))
  if (review) {
    issues.push(...review.uncovered.map((x) => `Not covered: ${x}`))
    issues.push(...review.unplanned.map((x) => `Not in the plan: ${x}`))
    issues.push(...review.unclear.map((x) => `Unclear: ${x}`))
  } else issues.push('The review did not finish')
  log(`Round ${round + 1}: ${draft.requirements.length} requirement(s), ${issues.length} issue(s)`)
  if (!issues.length) break
}

return {
  ready: issues.length === 0,
  files: draft.files,
  requirements: draft.requirements,
  formatVerdict: format ? format.verdict : 'not run',
  openIssues: issues,
  next: 'Read the spec files, edit them as you see fit, and commit them yourself. Then run aqv-build.',
}
