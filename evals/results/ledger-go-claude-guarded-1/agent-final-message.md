# The agent's final message

Copied from the run's agent log, which is not committed.

---

Ledgerline is built: all nine requirements are merged into `main`, and the verifier reports 9 of 9 at `Sync` and healthy at the latest commit (`8ac8f9e`). `go build ./... && go test ./...` passes.

The verifier's mutation check (T7) and its fuzz check (A7) only run in the final check, so they have not run yet. I ran Schemathesis myself against the running service with four seeds, and after the email fix below all generated cases passed.

Things you might not expect:

- **Email white space.** The fuzzer found that my first email check rejected addresses the contract's pattern allows. It took two fix branches to settle; the service now rejects only ASCII white space in an email, which is how Schemathesis reads `\s`. An address containing a no-break space is therefore accepted.
- **Dates are shape-checked only.** `paid_on` and `refunded_on` must match `YYYY-MM-DD`, as the contract's pattern says, but `0000-00-00` or `9999-99-99` are accepted. Rejecting impossible dates would be stricter than the contract.
- **Fuzzer cache committed by mistake.** One fix commit (`035ecf7`) picked up Schemathesis's `.schemathesis/` cache files. Since `main` cannot be rewritten, a follow-up `chore` commit removes them and adds `.schemathesis/` to `.gitignore`.
- **Merge commits.** Each merge has a Conventional Commits subject and carries the `Refs:` and `Co-Authored-By:` trailers, rather than git's default "Merge branch" message.
- **Extra branches.** Besides the nine feature branches there are two `fix/AC-led-001-…` branches for the email pattern and three small `test/…` branches (server environment fallbacks, concurrent payments, single database connection).
- **A repeat is still validated.** A request that repeats an Idempotency-Key must itself have a valid body, otherwise it gets 422 rather than the original payment.
- **A zero-total order stays "open".** No payment can be made against it, since the smallest payment is one cent.
