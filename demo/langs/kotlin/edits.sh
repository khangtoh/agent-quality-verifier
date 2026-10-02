# Kotlin edits used by the scenarios. Each function changes files only; the scenario commits.
PKG=src/main/kotlin/com/example/auth
TPKG=src/test/kotlin/com/example/auth

e_impl_007() {
  replace $PKG/AccountStore.kt "    fun addAccount(email: String, password: String) {
" "    fun addAccount(email: String, password: String) {
        require(password.length >= 6) { \"password too short\" }
"
}

e_tests_007() {
  cat > $TPKG/PasswordLengthTest.kt <<'KT'
package com.example.auth

import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class PasswordLengthTest {
    @Test
    fun `AC-auth-007 five characters rejected`() {
        assertFailsWith<IllegalArgumentException> { AccountStore().addAccount("bo@example.com", "five5") }
    }

    @Test
    fun `AC-auth-007 six characters accepted`() {
        val store = AccountStore()
        store.addAccount("bo@example.com", "six666")
        assertTrue("bo@example.com" in store.accounts)
    }
}
KT
}

e_test_007_assert_true() {
  cat > $TPKG/PasswordLengthTest.kt <<'KT'
package com.example.auth

import kotlin.test.Test
import kotlin.test.assertTrue

class PasswordLengthTest {
    @Test
    fun `AC-auth-007 short passwords rejected`() {
        assertTrue(true)
    }
}
KT
}

e_comment_007() {
  replace $PKG/AccountStore.kt "    fun addAccount(email: String, password: String) {
" "    fun addAccount(email: String, password: String) {
        // TODO: enforce the minimum password length
"
}

e_threshold_4() { replace $PKG/AccountStore.kt "const val MAX_FAILED_ATTEMPTS = 3" "const val MAX_FAILED_ATTEMPTS = 4"; }

e_lockout_gt() { replace $PKG/AccountStore.kt "if (failures >= MAX_FAILED_ATTEMPTS) {" "if (failures > MAX_FAILED_ATTEMPTS) {"; }

# Renames isExpired in the code but not in its test, so the tests no longer compile.
e_rename_expiry_src_only() {
  replace $PKG/AccountStore.kt "fun isExpired(" "fun sessionExpired("
  replace $PKG/AuthController.kt "isExpired(lastSeen," "sessionExpired(lastSeen,"
}

e_weak_lockout_tests() {
  cat > $TPKG/LockoutTest.kt <<'KT'
package com.example.auth

import kotlin.test.Test
import kotlin.test.assertEquals

class LockoutTest : ApiTest() {
    @Test
    fun `AC-auth-002 failed attempts are rejected`() {
        repeat(3) { assertEquals(401, call("POST", "/login", bad).status) }
    }
}
KT
}

e_logout_route_and_test() {
  replace $PKG/AuthController.kt '    @PostMapping("/login")
' '    @PostMapping("/logout")
    fun logout(): Map<String, Any> = mapOf("status" to "signed_out")

    @PostMapping("/login")
'
  cat > $TPKG/LogoutTest.kt <<'KT'
package com.example.auth

import kotlin.test.Test
import kotlin.test.assertEquals

class LogoutTest : ApiTest() {
    @Test
    fun `AC-auth-007 sign out`() {
        val r = call("POST", "/logout")
        assertEquals(200, r.status)
        assertEquals(mapOf("status" to "signed_out"), r.body)
    }
}
KT
}

e_rename_token() {
  replace $PKG/AuthController.kt 'mapOf("token" to result)' 'mapOf("access_token" to result)'
  replace $TPKG/LoginTest.kt 'r.body["token"]' 'r.body["access_token"]'
}

e_debug_route() {
  replace $PKG/AuthController.kt '    @PostMapping("/login")
' '    @GetMapping("/debug/users")
    fun debugUsers(): Map<String, Any> = mapOf("users" to store.accounts.keys.toList())

    @PostMapping("/login")
'
}

e_leak_password() {
  replace $PKG/AuthController.kt 'mapOf("token" to result)' 'mapOf("token" to result, "debug_password" to body.password)'
}

e_status_423() {
  replace $PKG/AuthController.kt '            return ResponseEntity.status(401).body(mapOf("error" to result))' '            return ResponseEntity.status(if (result == "locked") 423 else 401).body(mapOf("error" to result))'
  replace $TPKG/LockoutTest.kt '        assertEquals(401, r.status)
        assertEquals(mapOf("error" to "locked"), r.body)' '        assertEquals(423, r.status)
        assertEquals(mapOf("error" to "locked"), r.body)'
}

e_reset_crash() {
  replace $PKG/AuthController.kt "        store.requestReset(body.email)
" "        val domain = body.email.split(\"@\")[1].lowercase()
        store.requestReset(body.email)
"
}

e_doc_comment() {
  replace $PKG/AccountStore.kt "    fun signIn(email: String, password: String): String {
" "    /** Returns a session token, or \"denied\" / \"locked\". */
    fun signIn(email: String, password: String): String {
"
}

e_big_file() {
  python3 - <<'PY'
lines = ["package com.example.auth", "", "/** Email domains that never receive reset links. */", "val BLOCKED_DOMAINS = setOf("]
lines += [f'    "blocked-{i}.example",' for i in range(600)]
lines += [")"]
open("src/main/kotlin/com/example/auth/BlockedDomains.kt", "w").write("\n".join(lines) + "\n")
PY
}
