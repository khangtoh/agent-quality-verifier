export const meta = {
  name: 'aqv-build',
  description: 'Build the committed requirements one at a time, each on its own branch and gated by aqv check',
  whenToUse: 'The spec is committed on main and some requirements are not yet Sync',
  phases: [
    { title: 'Preflight', detail: 'clean main, valid spec, current status of every requirement' },
    { title: 'Build', detail: 'per requirement: branch, contract, code and tests, aqv check, fix, merge' },
    { title: 'Report', detail: 'aqv check over all history on main' },
  ],
}

// args: { aqv, main, skip, finalSkip, only: [ids], maxFix, continueOnBlocked, record }
// Requirements are built in spec order and one at a time: each one branches from main and is merged
// back before the next starts, so the history reads the way the verifier expects.
const a = args || {}
const AQV = a.aqv || 'aqv'
const MAIN = a.main || 'main'
const SKIP = a.skip || ''
const FINAL_SKIP = a.finalSkip === undefined ? SKIP : a.finalSkip
const MAX_FIX = a.maxFix === undefined ? 2 : a.maxFix
const flag = (skip) => (skip ? ` --skip ${skip}` : '')

const FAILURES = {
  type: 'array',
  items: {
    type: 'object',
    required: ['check', 'scope', 'subject', 'summary'],
    properties: {
      check: { type: 'string' },
      scope: { type: 'string' },
      subject: { type: 'string' },
      summary: { type: 'string' },
    },
  },
}
const PRE = {
  type: 'object',
  required: ['ok', 'problems', 'requirements', 'failures'],
  properties: {
    ok: { type: 'boolean' },
    problems: { type: 'array', items: { type: 'string' } },
    requirements: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'text', 'api', 'status'],
        properties: {
          id: { type: 'string' },
          text: { type: 'string' },
          api: { type: 'array', items: { type: 'string' } },
          status: { type: 'string' },
        },
      },
    },
    failures: FAILURES,
  },
}
const BUILT = {
  type: 'object',
  required: ['branch', 'commits', 'summary'],
  properties: {
    branch: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    blocked: { type: 'string' },
  },
}
const GATE = {
  type: 'object',
  required: ['ran', 'branch', 'dirty', 'statuses', 'failures'],
  properties: {
    ran: { type: 'boolean' },
    branch: { type: 'string' },
    dirty: { type: 'boolean' },
    statuses: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'status'],
        properties: { id: { type: 'string' }, status: { type: 'string' } },
      },
    },
    failures: FAILURES,
  },
}
const MERGED = {
  type: 'object',
  required: ['merged', 'detail'],
  properties: { merged: { type: 'boolean' }, detail: { type: 'string' } },
}
const FINAL = {
  type: 'object',
  required: ['ran', 'statuses', 'failing', 'notCovered', 'report'],
  properties: {
    ran: { type: 'boolean' },
    statuses: GATE.properties.statuses,
    failing: { type: 'array', items: { type: 'string' } },
    notCovered: { type: 'array', items: { type: 'string' } },
    report: { type: 'string' },
  },
}

const READ_RESULTS = `Read .aqv-out/results.json with jq or python3 and copy values verbatim:
- statuses: id and status of every entry in "requirements".
- failures: check, scope, subject and summary of every entry in "results" whose verdict is "fail" or "error".`

const RULES = `
Rules the verifier checks. Read .aqv.yml for this repository's paths, limits and runner commands.
- Branch: created from ${MAIN}, named to match git.branch_pattern, e.g. feat/AC-auth-002-lockout.
- Contract first, when the requirement has an API operation: a commit that adds or changes the operation in
  the contract file, with \`x-requirements: [<ID>]\` on it, a schema for every response body, and
  \`additionalProperties: false\` on object schemas.
- Tests carry the ID in their name, in the form the language uses: test_AC_auth_002_x,
  TestAC_auth_002_X, ac_auth_002_x, "AC-auth-002 x". They must run this requirement's code and assert
  on what it does, so that breaking any one of its lines fails a test: cover boundaries and error paths.
- If the repository has a helper that records HTTP responses for the verifier (tools/aqvcapture,
  aqvRecord or a capture setup file), every HTTP request in a test goes through it.
- Commits: a Conventional Commits subject (feat(scope): ..., fix(scope): ...), the trailer
  \`Refs: <ID>\` naming this requirement only, and your Co-Authored-By trailer. Stay under
  git.max_commit_lines changed lines per commit. Do not turn off commit signing.
- Never edit the spec files, the ID registry, .aqv.yml or the lint ruleset, and never rewrite ${MAIN}.
  If the requirement cannot be met as written, stop and say why in "blocked".`

phase('Preflight')
const pre = await agent(
  `Check that this repository is ready to build requirements, and report where each one stands. Change
nothing except by running the verifier, which writes to .aqv-out/.

Report a problem for each of these that does not hold:
- The current branch is ${MAIN} and \`git status --porcelain\` is empty.
- .aqv.yml and the spec files it names are committed.
- .aqv-out/ is ignored by git (git check-ignore -q .aqv-out).
- \`${AQV} check --repo . --only T1\` exits 0. Quote its T1 line if it does not.

Then run \`${AQV} check --repo .${flag(SKIP)}\`. It is expected to exit non-zero while requirements are
unbuilt; that is not a problem.
${READ_RESULTS}
Return requirements in file order with id, text, api and status. ok is true only when there are no problems.`,
  { label: 'preflight', effort: 'low', schema: PRE },
)
if (!pre) return { built: [], blocked: [], problems: ['The preflight agent did not finish'] }
if (!pre.ok) {
  log(`Not ready: ${pre.problems.join('; ')}`)
  return { built: [], blocked: [], problems: pre.problems }
}

const isReq = new Set(pre.requirements.map((r) => r.id))
const baseline = pre.failures.filter((f) => !isReq.has(f.subject))
if (baseline.length)
  log(`Already failing on ${MAIN}, and will fail the final report: ${baseline.map((f) => `${f.check} ${f.summary}`).join(' | ')}`)

const unbuilt = pre.requirements.filter((r) => r.status !== 'Sync')
const todo = a.only ? unbuilt.filter((r) => a.only.includes(r.id)) : unbuilt
if (a.only && todo.length < unbuilt.length)
  log(`Building ${todo.length} of ${unbuilt.length} unbuilt requirement(s); the rest are left for another run`)
const pending = new Set(unbuilt.map((r) => r.id))

const describe = (r) => `${r.id}: ${r.text}${r.api.length ? `\nAPI: ${r.api.join(', ')}` : ''}`

// A requirement passes when it is Sync and nothing fails except requirements that are not built yet.
const judge = (g, rid) => {
  if (!g || !g.ran) return { pass: false, blocking: [{ check: '-', scope: 'run', subject: rid, summary: 'aqv check did not run' }] }
  const blocking = g.failures.filter((f) => !(f.scope === 'requirement' && f.subject !== rid && pending.has(f.subject)))
  if (g.dirty) blocking.push({ check: '-', scope: 'tree', subject: rid, summary: 'uncommitted changes; the verifier reads commits' })
  const status = (g.statuses.find((s) => s.id === rid) || {}).status || 'unknown'
  if (status !== 'Sync' && !blocking.length)
    blocking.push({ check: '-', scope: 'requirement', subject: rid, summary: `status is ${status}` })
  return { pass: status === 'Sync' && blocking.length === 0, status, blocking }
}

const gate = (r, branch, n) =>
  agent(
    `Run the verifier on branch ${branch} and report what it says. Do not change any file or commit.

  git checkout -q ${branch}
  ${AQV} check --repo . --base ${MAIN}${flag(SKIP)}

A non-zero exit is expected while other requirements are unbuilt. ran is false only if the verifier
did not write .aqv-out/results.json. branch is the output of \`git branch --show-current\`, and dirty is
true when \`git status --porcelain\` prints anything.
${READ_RESULTS}`,
    { label: `check ${r.id}${n ? ` (${n})` : ''}`, phase: 'Build', effort: 'low', schema: GATE },
  )

phase('Build')
const built = []
const blocked = []
for (let i = 0; i < todo.length; i++) {
  const r = todo[i]
  const work = await agent(
    `Implement one requirement in this repository, then stop.

${describe(r)}

Start from a clean ${MAIN}. Read the plan and the existing code first. Build only this requirement: the
branch, the contract commit if it has an API operation, then the code and its tests.
${RULES}

Run the test suite before you finish. Leave the working tree clean and stay on your branch; do not
merge. Return the branch name, your commit subjects, and one sentence on what you built.`,
    { label: `build ${r.id}`, phase: 'Build', schema: BUILT },
  )
  let verdict = { pass: false, status: 'unknown', blocking: [{ check: '-', scope: 'run', subject: r.id, summary: 'the build agent did not finish' }] }
  if (work && work.blocked) verdict.blocking = [{ check: '-', scope: 'requirement', subject: r.id, summary: work.blocked }]
  else if (work) {
    verdict = judge(await gate(r, work.branch, 0), r.id)
    for (let n = 1; n <= MAX_FIX && !verdict.pass; n++) {
      await agent(
        `The verifier rejected the work for one requirement on branch ${work.branch}. Fix it there with new commits.

${describe(r)}

What failed:
${verdict.blocking.map((f) => `- ${f.check} (${f.subject}): ${f.summary}`).join('\n')}

.aqv-out/report.txt has the full output. Fix the cause in the code or the tests. Do not weaken or
delete a test to get a pass, and do not change the spec, .aqv.yml or the checks that are run.
${RULES}

Leave the working tree clean and stay on ${work.branch}.`,
        { label: `fix ${r.id} (${n})`, phase: 'Build' },
      )
      verdict = judge(await gate(r, work.branch, n), r.id)
    }
  }

  if (verdict.pass) {
    const m = await agent(
      `Merge a verified branch. Run exactly:

  git checkout -q ${MAIN}
  git merge --no-ff -m "Merge branch '${work.branch}'" ${work.branch}

Do not resolve conflicts or change files: if the merge does not complete cleanly, run
\`git merge --abort\` and return merged false with the reason.`,
      { label: `merge ${r.id}`, phase: 'Build', effort: 'low', schema: MERGED },
    )
    if (m && m.merged) {
      pending.delete(r.id)
      built.push({ id: r.id, branch: work.branch, summary: work.summary })
      log(`${r.id} is Sync and merged (${built.length} of ${todo.length})`)
      continue
    }
    verdict = { pass: false, status: verdict.status, blocking: [{ check: '-', scope: 'merge', subject: r.id, summary: m ? m.detail : 'the merge agent did not finish' }] }
  }

  blocked.push({ id: r.id, branch: work ? work.branch : null, status: verdict.status, why: verdict.blocking })
  log(`${r.id} is blocked: ${verdict.blocking.map((f) => `${f.check} ${f.summary}`).join(' | ')}`)
  if (!a.continueOnBlocked) {
    const left = todo.slice(i + 1).map((x) => x.id)
    if (left.length) log(`Stopping here; not attempted: ${left.join(', ')}`)
    break
  }
}

phase('Report')
const final = await agent(
  `Run the verifier over all history on ${MAIN} and report what it says. Do not change any file or commit.

  git checkout -q ${MAIN}
  ${AQV} check --repo .${flag(FINAL_SKIP)}${a.record === false ? '' : ' --record'}

ran is false only if the verifier did not write .aqv-out/results.json. From that file return: statuses
(id and status of every entry in "requirements"), failing (the keys of "checks" whose value is "fail"
or "error"), notCovered (the keys whose value is "not_covered"), and report (the absolute path of
.aqv-out/report.html).`,
  { label: 'final check', effort: 'low', schema: FINAL },
)

return {
  built,
  blocked,
  notAttempted: todo.filter((r) => !built.some((b) => b.id === r.id) && !blocked.some((b) => b.id === r.id)).map((r) => r.id),
  final,
}
