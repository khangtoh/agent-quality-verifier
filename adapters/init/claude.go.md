<!-- aqv:start -->
## Agent Quality Verifier

`aqv` checks this project against its spec: every requirement must have code, tagged tests that
prove it, and a commit history that says which requirement each change serves. Check your work with
`aqv check --repo . --base main` on a branch; the result is in `.aqv-out/report.txt` and
`.aqv-out/report.html`. `.aqv.yml` has the paths, limits and commands.

**Never edit** `specs/`, `.aqv.yml` or `.spectral.yaml` unless the user asks for that change. If a
requirement cannot be met as written, stop and say so.

**Spec.** One requirement per line in `specs/*.md`:
`- **AC-auth-002** (api: POST /login): Accounts lock after 3 consecutive failed sign-in attempts.`
The ID is `AC-<area>-<nnn>`, and every ID ever issued is a line in `specs/.ids` and is never reused.
`(api: METHOD /path)` marks a requirement an HTTP endpoint serves.

**One requirement at a time.** Work on a branch from `main` named like `feat/AC-auth-002-lockout`,
and merge it with a merge commit (`git merge --no-ff`).

**Contract first.** For a requirement with an API operation, first commit the operation to
`contracts/openapi.yaml` with `x-requirements: [AC-auth-002]`, a schema for every response body, and
`additionalProperties: false` on object schemas.

**Code.** Code lives in `internal/` and `cmd/`. The service is the main package `cmd/server` and
listens on the port in `$PORT`.

**Tests.** Name each test after its requirement: `TestAC_auth_002_LocksAfterThreeFailures`. The
tagged tests must run the requirement's code and assert on what it does, so that breaking any one of
its lines fails a test: cover boundaries and error paths. Send every HTTP request in a test through
`aqvcapture.Do(t, handler, req)` from this module's `tools/aqvcapture` package (or call
`aqvcapture.Record` after a request made another way), so responses are checked against the contract.

**Commits.** A Conventional Commits subject (`feat(auth): lock accounts after 3 failed attempts`),
the trailer `Refs: AC-auth-002` naming one requirement, and your `Co-Authored-By:` trailer. A
`refactor` or `chore` commit that changes code uses `Refs: none` and must not change behaviour. Keep
each commit under 400 changed lines, leave commit signing on, and never rewrite `main`.
<!-- aqv:end -->
