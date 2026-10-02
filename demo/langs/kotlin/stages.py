"""Kotlin demo: Spring Boot 3 service, JUnit 5 + MockMvc tests, Gradle JUnit XML, JaCoCo coverage, springdoc."""
from ..common import aqv_config, d

NAME = "Kotlin"
STACK = "Kotlin 2.0 · Spring Boot 3.4 · JUnit 5 + MockMvc · Gradle · JaCoCo · springdoc"
JOBS = 2

PKG = "src/main/kotlin/com/example/auth"
TPKG = "src/test/kotlin/com/example/auth"

AQV_CONFIG = aqv_config(["src/main/"], ["src/test/"], d("""
    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "gradle -q --console=plain test {extra} {filter}"
      junit_dir: build/test-results/test
      coverage: "gradle -q --console=plain test -Paqv.ignoreFailures=true {filter} jacocoTestReport"
      coverage_out: build/reports/jacoco/test/jacocoTestReport.xml
      coverage_format: jacoco
      coverage_source_roots: ["src/main/kotlin"]
      filter: "--tests '*{id}*'"
      select_nothing: "--tests 'aqv.NoSuchTest'"
      comment_prefix: ["//", "/*", "*"]

    api:
      openapi_url: /v3/api-docs
      serve: "gradle -q bootJar && java -jar build/libs/auth-service-0.1.0.jar --server.port={port} --server.address=127.0.0.1"
      serve_timeout: 600
      capture: true
      capture_extra: "-Paqv.capture=$AQV_CAPTURE_OUT"

    mutation:
      family: c
      build: "gradle -q --console=plain compileTestKotlin"
      min_kill_ratio: 0.6
      max_mutants: 10
"""))

SETTINGS = d('''
    pluginManagement {
        repositories {
            maven("https://maven-central.storage-download.googleapis.com/maven2/")
            gradlePluginPortal()
        }
    }

    rootProject.name = "auth-service"
''')

BUILD = d('''
    plugins {
        kotlin("jvm") version "2.0.21"
        kotlin("plugin.spring") version "2.0.21"
        id("org.springframework.boot") version "3.4.1"
        jacoco
    }

    group = "com.example"
    version = "0.1.0"

    repositories {
        // Google's mirror of Maven Central first; Maven Central rate-limits bursts of downloads.
        maven("https://maven-central.storage-download.googleapis.com/maven2/")
        mavenCentral()
    }

    dependencies {
        implementation(platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES))
        testImplementation(platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES))
        implementation("org.springframework.boot:spring-boot-starter-web")
        implementation("com.fasterxml.jackson.module:jackson-module-kotlin")
        implementation("org.jetbrains.kotlin:kotlin-reflect")
        implementation("org.springdoc:springdoc-openapi-starter-webmvc-api:2.7.0")
        testImplementation("org.springframework.boot:spring-boot-starter-test")
        testImplementation("org.jetbrains.kotlin:kotlin-test-junit5")
        testRuntimeOnly("org.junit.platform:junit-platform-launcher")
    }

    tasks.test {
        useJUnitPlatform()
        filter { isFailOnNoMatchingTests = false }
        outputs.upToDateWhen { false }
        ignoreFailures = project.hasProperty("aqv.ignoreFailures")
        // Agent Quality Verifier A6 adapter: where AqvCapture writes test traffic.
        systemProperty("aqv.capture", project.findProperty("aqv.capture") ?: "")
    }

    tasks.jacocoTestReport {
        reports { xml.required = true }
    }
''')

# A6 adapter, vendored by the human: the test base class calls AqvCapture.record after each request.
CAPTURE = d('''
    package com.example.auth

    import com.fasterxml.jackson.databind.ObjectMapper
    import java.io.File

    /**
     * A6 adapter for the Agent Quality Verifier. Test helpers call [record] after each request;
     * when the aqv.capture system property names a file, the response is appended as one JSON line.
     */
    object AqvCapture {
        private val json = ObjectMapper()

        @Synchronized
        fun record(test: String, method: String, path: String, status: Int, body: String) {
            val out = System.getProperty("aqv.capture").orEmpty()
            if (out.isBlank()) return
            val parsed: Any? = runCatching { json.readValue(body, Any::class.java) }.getOrDefault(body)
            val line = json.writeValueAsString(
                mapOf("test" to test, "method" to method, "path" to path, "status" to status, "body" to parsed),
            )
            File(out).appendText(line + "\\n")
        }
    }
''')

# ---------------------------------------------------------------------------
# Code, one version per requirement
# ---------------------------------------------------------------------------

STORE_1 = d('''
    package com.example.auth

    import java.security.SecureRandom

    private val random = SecureRandom()

    fun newToken(): String {
        val bytes = ByteArray(16)
        random.nextBytes(bytes)
        return bytes.joinToString("") { "%02x".format(it) }
    }

    class AccountStore {
        val accounts = mutableMapOf<String, String>()

        fun addAccount(email: String, password: String) {
            accounts[email] = password
        }

        fun signIn(email: String, password: String): String {
            if (accounts[email] == password) {
                return newToken()
            }
            return "denied"
        }

        companion object {
            fun withDemoAccounts(): AccountStore {
                val store = AccountStore()
                store.addAccount("ada@example.com", "correct horse")
                return store
            }
        }
    }
''')

STORE_2 = (
    STORE_1.replace("private val random = SecureRandom()\n",
                    "const val MAX_FAILED_ATTEMPTS = 3\n\nprivate val random = SecureRandom()\n")
    .replace("    val accounts = mutableMapOf<String, String>()\n",
             "    val accounts = mutableMapOf<String, String>()\n"
             "    val failed = mutableMapOf<String, Int>()\n"
             "    val locked = mutableSetOf<String>()\n")
    .replace(
        "    fun signIn(email: String, password: String): String {\n"
        "        if (accounts[email] == password) {\n"
        "            return newToken()\n"
        "        }\n",
        "    fun signIn(email: String, password: String): String {\n"
        "        if (email in locked) {\n"
        '            return "locked"\n'
        "        }\n"
        "        if (accounts[email] == password) {\n"
        "            failed[email] = 0\n"
        "            return newToken()\n"
        "        }\n"
        "        val failures = (failed[email] ?: 0) + 1\n"
        "        failed[email] = failures\n"
        "        if (failures >= MAX_FAILED_ATTEMPTS) {\n"
        "            locked.add(email)\n"
        "        }\n",
    )
)

STORE_3 = STORE_2.replace(
    "const val MAX_FAILED_ATTEMPTS = 3\n",
    "const val MAX_FAILED_ATTEMPTS = 3\nconst val SESSION_TTL_SECONDS = 30 * 60L\n\n"
    "fun isExpired(lastSeen: Long, now: Long): Boolean = now - lastSeen > SESSION_TTL_SECONDS\n",
)

STORE_4 = STORE_3.replace(
    "    val locked = mutableSetOf<String>()\n",
    "    val locked = mutableSetOf<String>()\n    val resetOutbox = mutableListOf<String>()\n",
).replace(
    '        return "denied"\n    }\n\n    companion object {\n',
    '        return "denied"\n    }\n\n'
    "    fun requestReset(email: String): Boolean {\n"
    "        if (email in accounts) {\n"
    "            resetOutbox.add(email)\n"
    "            return true\n"
    "        }\n"
    "        return false\n"
    "    }\n\n    companion object {\n",
)

STORE_5 = STORE_4.replace(
    "    fun requestReset(email: String): Boolean {\n"
    "        if (email in accounts) {\n"
    "            resetOutbox.add(email)\n"
    "            return true\n"
    "        }\n"
    "        return false\n"
    "    }\n",
    "    fun requestReset(email: String) {\n"
    "        if (email in accounts) {\n"
    "            resetOutbox.add(email)\n"
    "        }\n"
    "    }\n",
)

STORE_6 = (
    STORE_5.replace("import java.security.SecureRandom\n",
                    "import java.security.MessageDigest\nimport java.security.SecureRandom\n")
    .replace(
        "fun isExpired(",
        "data class Credential(val salt: String, val digest: String)\n\n"
        "fun hashPassword(password: String, salt: String): String =\n"
        '    MessageDigest.getInstance("SHA-256").digest((salt + password).toByteArray())\n'
        '        .joinToString("") { "%02x".format(it) }\n\n'
        "fun isExpired(",
    )
    .replace("    val accounts = mutableMapOf<String, String>()\n",
             "    val accounts = mutableMapOf<String, Credential>()\n")
    .replace(
        "    fun addAccount(email: String, password: String) {\n        accounts[email] = password\n    }\n",
        "    fun addAccount(email: String, password: String) {\n"
        "        val bytes = ByteArray(8)\n"
        "        random.nextBytes(bytes)\n"
        '        val salt = bytes.joinToString("") { "%02x".format(it) }\n'
        "        accounts[email] = Credential(salt, hashPassword(password, salt))\n"
        "    }\n\n"
        "    private fun passwordMatches(email: String, password: String): Boolean {\n"
        "        val credential = accounts[email] ?: return false\n"
        "        return hashPassword(password, credential.salt) == credential.digest\n"
        "    }\n",
    )
    .replace("        if (accounts[email] == password) {\n", "        if (passwordMatches(email, password)) {\n")
)

ERRORS = d('''
    package com.example.auth

    import org.springframework.http.ResponseEntity
    import org.springframework.http.converter.HttpMessageNotReadableException
    import org.springframework.web.bind.MissingServletRequestParameterException
    import org.springframework.web.bind.annotation.ExceptionHandler
    import org.springframework.web.bind.annotation.RestControllerAdvice
    import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException

    fun invalid(): ResponseEntity<Map<String, Any>> =
        ResponseEntity.status(400).body(mapOf("error" to "invalid_request"))

    @RestControllerAdvice
    class ApiErrors {
        @ExceptionHandler(
            HttpMessageNotReadableException::class,
            MissingServletRequestParameterException::class,
            MethodArgumentTypeMismatchException::class,
        )
        fun badRequest(): ResponseEntity<Map<String, Any>> = invalid()
    }
''')

APPLICATION = d('''
    package com.example.auth

    import org.springframework.boot.autoconfigure.SpringBootApplication
    import org.springframework.boot.runApplication
    import org.springframework.context.annotation.Bean

    @SpringBootApplication
    class Application {
        @Bean
        fun accountStore(): AccountStore = AccountStore.withDemoAccounts()
    }

    fun main(args: Array<String>) {
        runApplication<Application>(*args)
    }
''')

CONTROLLER_1 = d('''
    package com.example.auth

    import org.springframework.http.ResponseEntity
    import org.springframework.web.bind.annotation.PostMapping
    import org.springframework.web.bind.annotation.RequestBody
    import org.springframework.web.bind.annotation.RestController

    data class Credentials(val email: String, val password: String)

    @RestController
    class AuthController(private val store: AccountStore) {
        @PostMapping("/login")
        fun login(@RequestBody body: Credentials): ResponseEntity<Map<String, Any>> {
            val result = store.signIn(body.email, body.password)
            if (result == "denied") {
                return ResponseEntity.status(401).body(mapOf("error" to result))
            }
            return ResponseEntity.ok(mapOf("token" to result))
        }
    }
''')

CONTROLLER_2 = CONTROLLER_1.replace('        if (result == "denied") {\n',
                                    '        if (result == "denied" || result == "locked") {\n')

CONTROLLER_3 = (
    CONTROLLER_2.replace("import org.springframework.web.bind.annotation.PostMapping\n",
                         "import org.springframework.web.bind.annotation.GetMapping\n"
                         "import org.springframework.web.bind.annotation.PostMapping\n")
    .replace("import org.springframework.web.bind.annotation.RequestBody\n",
             "import org.springframework.web.bind.annotation.RequestBody\n"
             "import org.springframework.web.bind.annotation.RequestParam\n")
    .replace(
        '        return ResponseEntity.ok(mapOf("token" to result))\n    }\n',
        '        return ResponseEntity.ok(mapOf("token" to result))\n    }\n\n'
        '    @GetMapping("/session")\n'
        '    fun session(@RequestParam("last_seen") lastSeen: Long): ResponseEntity<Map<String, Any>> {\n'
        "        if (lastSeen < 0 || lastSeen > 4102444800L) {\n"
        "            return invalid()\n"
        "        }\n"
        '        return ResponseEntity.ok(mapOf("expired" to isExpired(lastSeen, System.currentTimeMillis() / 1000)))\n'
        "    }\n",
    )
)

CONTROLLER_4 = (
    CONTROLLER_3.replace("data class Credentials(val email: String, val password: String)\n",
                         "data class Credentials(val email: String, val password: String)\n\n"
                         "data class ResetRequest(val email: String)\n")
    .replace(
        '        return ResponseEntity.ok(mapOf("expired" to isExpired(lastSeen, System.currentTimeMillis() / 1000)))\n    }\n',
        '        return ResponseEntity.ok(mapOf("expired" to isExpired(lastSeen, System.currentTimeMillis() / 1000)))\n    }\n\n'
        '    @PostMapping("/password-reset")\n'
        "    fun passwordReset(@RequestBody body: ResetRequest): ResponseEntity<Map<String, Any>> {\n"
        "        val sent = store.requestReset(body.email)\n"
        '        return ResponseEntity.status(202).body(mapOf("status" to if (sent) "sent" else "unknown_email"))\n'
        "    }\n",
    )
)

CONTROLLER_5 = CONTROLLER_4.replace(
    "        val sent = store.requestReset(body.email)\n"
    '        return ResponseEntity.status(202).body(mapOf("status" to if (sent) "sent" else "unknown_email"))\n',
    "        store.requestReset(body.email)\n"
    '        return ResponseEntity.status(202).body(mapOf("status" to "sent"))\n',
)

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

API_TEST = d('''
    package com.example.auth

    import com.fasterxml.jackson.databind.ObjectMapper
    import org.junit.jupiter.api.BeforeEach
    import org.junit.jupiter.api.TestInfo
    import org.springframework.http.HttpMethod
    import org.springframework.http.MediaType
    import org.springframework.test.web.servlet.MockMvc
    import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request
    import org.springframework.test.web.servlet.setup.MockMvcBuilders

    abstract class ApiTest {
        protected lateinit var store: AccountStore
        private lateinit var mvc: MockMvc
        private lateinit var testName: String
        private val json = ObjectMapper()

        @BeforeEach
        fun setUp(info: TestInfo) {
            testName = info.testMethod.map { it.name }.orElse(info.displayName)
            store = AccountStore.withDemoAccounts()
            mvc = MockMvcBuilders.standaloneSetup(AuthController(store)).setControllerAdvice(ApiErrors()).build()
        }

        data class Response(val status: Int, val body: Map<*, *>)

        protected fun call(method: String, path: String, body: Any? = null): Response {
            val req = request(HttpMethod.valueOf(method), path)
            if (body != null) {
                req.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body))
            }
            val res = mvc.perform(req).andReturn().response
            val text = res.contentAsString
            AqvCapture.record(testName, method, path, res.status, text)
            val parsed = if (text.isBlank()) emptyMap<Any, Any>() else json.readValue(text, Map::class.java)
            return Response(res.status, parsed)
        }

        protected val good = mapOf("email" to "ada@example.com", "password" to "correct horse")
        protected val bad = mapOf("email" to "ada@example.com", "password" to "wrong")
    }
''')

TEST_LOGIN = d('''
    package com.example.auth

    import kotlin.test.Test
    import kotlin.test.assertEquals

    class LoginTest : ApiTest() {
        @Test
        fun `AC-auth-001 sign in returns a token`() {
            val r = call("POST", "/login", good)
            assertEquals(200, r.status)
            assertEquals(32, (r.body["token"] as String).length)
        }

        @Test
        fun `AC-auth-001 wrong password is denied`() {
            val r = call("POST", "/login", bad)
            assertEquals(401, r.status)
            assertEquals(mapOf("error" to "denied"), r.body)
        }

        @Test
        fun `AC-auth-001 malformed request is rejected`() {
            val r = call("POST", "/login", mapOf("email" to "ada@example.com"))
            assertEquals(400, r.status)
            assertEquals(mapOf("error" to "invalid_request"), r.body)
        }
    }
''')

TEST_LOCKOUT = d('''
    package com.example.auth

    import kotlin.test.Test
    import kotlin.test.assertEquals

    class LockoutTest : ApiTest() {
        private fun fail(times: Int) = repeat(times) { call("POST", "/login", bad) }

        @Test
        fun `AC-auth-002 locks after three failures`() {
            fail(3)
            val r = call("POST", "/login", good)
            assertEquals(401, r.status)
            assertEquals(mapOf("error" to "locked"), r.body)
        }

        @Test
        fun `AC-auth-002 two failures do not lock`() {
            fail(2)
            assertEquals(200, call("POST", "/login", good).status)
        }

        @Test
        fun `AC-auth-002 success resets the count`() {
            fail(2)
            call("POST", "/login", good)
            fail(2)
            assertEquals(200, call("POST", "/login", good).status)
        }
    }
''')

TEST_SESSION = d('''
    package com.example.auth

    import kotlin.test.Test
    import kotlin.test.assertEquals
    import kotlin.test.assertFalse
    import kotlin.test.assertTrue

    class SessionTest : ApiTest() {
        private fun now() = System.currentTimeMillis() / 1000

        @Test
        fun `AC-auth-003 expired after 30 minutes`() {
            val r = call("GET", "/session?last_seen=${now() - 31 * 60}")
            assertEquals(200, r.status)
            assertEquals(mapOf("expired" to true), r.body)
        }

        @Test
        fun `AC-auth-003 active within 30 minutes`() {
            val r = call("GET", "/session?last_seen=${now() - 29 * 60}")
            assertEquals(mapOf("expired" to false), r.body)
        }

        @Test
        fun `AC-auth-003 boundary is exactly 30 minutes`() {
            assertFalse(isExpired(0, 30 * 60))
            assertTrue(isExpired(0, 30 * 60 + 1))
        }

        @Test
        fun `AC-auth-003 rejects a bad last_seen and accepts the edges`() {
            for (bad in listOf("soon", "-1", "4102444801")) {
                val r = call("GET", "/session?last_seen=$bad")
                assertEquals(400, r.status, bad)
                assertEquals(mapOf("error" to "invalid_request"), r.body)
            }
            for (edge in listOf("0", "4102444800")) {
                assertEquals(200, call("GET", "/session?last_seen=$edge").status, edge)
            }
        }
    }
''')

TEST_RESET_4 = d('''
    package com.example.auth

    import kotlin.test.Test
    import kotlin.test.assertEquals
    import kotlin.test.assertTrue

    class ResetTest : ApiTest() {
        @Test
        fun `AC-auth-004 link sent for a known email`() {
            val r = call("POST", "/password-reset", mapOf("email" to "ada@example.com"))
            assertEquals(202, r.status)
            assertEquals(listOf("ada@example.com"), store.resetOutbox)
        }

        @Test
        fun `AC-auth-004 no link for an unknown email`() {
            call("POST", "/password-reset", mapOf("email" to "nobody@example.com"))
            assertTrue(store.resetOutbox.isEmpty())
        }
    }
''')

TEST_RESET_5 = TEST_RESET_4.replace(
    "        assertTrue(store.resetOutbox.isEmpty())\n    }\n}\n",
    "        assertTrue(store.resetOutbox.isEmpty())\n    }\n"
    "\n"
    "    @Test\n"
    "    fun `AC-auth-005 same response for an unknown email`() {\n"
    '        val known = call("POST", "/password-reset", mapOf("email" to "ada@example.com"))\n'
    '        val unknown = call("POST", "/password-reset", mapOf("email" to "nobody@example.com"))\n'
    "        assertEquals(202, known.status)\n"
    '        assertEquals(mapOf("status" to "sent"), known.body)\n'
    "        assertEquals(known, unknown)\n"
    "    }\n"
    "\n"
    "    @Test\n"
    "    fun `AC-auth-005 known email still gets its link`() {\n"
    '        call("POST", "/password-reset", mapOf("email" to "nobody@example.com"))\n'
    '        call("POST", "/password-reset", mapOf("email" to "ada@example.com"))\n'
    '        assertEquals(listOf("ada@example.com"), store.resetOutbox)\n'
    "    }\n}\n",
)

TEST_STORAGE = d('''
    package com.example.auth

    import kotlin.test.Test
    import kotlin.test.assertEquals
    import kotlin.test.assertNotEquals
    import kotlin.test.assertTrue

    class StorageTest {
        @Test
        fun `AC-auth-006 password not stored in plain text`() {
            val store = AccountStore()
            store.addAccount("bo@example.com", "s3cret")
            val c = store.accounts.getValue("bo@example.com")
            assertNotEquals("s3cret", c.salt)
            assertNotEquals("s3cret", c.digest)
            assertEquals(hashPassword("s3cret", c.salt), c.digest)
        }

        @Test
        fun `AC-auth-006 hashed password still signs in`() {
            val store = AccountStore()
            store.addAccount("bo@example.com", "s3cret")
            assertTrue(store.signIn("bo@example.com", "s3cret") !in listOf("denied", "locked"))
            assertEquals("denied", store.signIn("bo@example.com", "nope"))
            assertEquals("denied", store.signIn("nobody@example.com", "s3cret"))
        }

        @Test
        fun `AC-auth-006 same password gets different salts`() {
            val store = AccountStore()
            store.addAccount("a@example.com", "s3cret")
            store.addAccount("b@example.com", "s3cret")
            assertNotEquals(store.accounts.getValue("a@example.com").salt, store.accounts.getValue("b@example.com").salt)
        }
    }
''')

# ---------------------------------------------------------------------------
# What the builder needs
# ---------------------------------------------------------------------------

GITIGNORE = "build/\n.gradle/\n.kotlin/\n.aqv-out/\n"

SCAFFOLD = {"settings.gradle.kts": SETTINGS, "build.gradle.kts": BUILD, ".aqv.yml": AQV_CONFIG,
            f"{TPKG}/AqvCapture.kt": CAPTURE}

CODE = {
    "AC-auth-001": {f"{PKG}/AccountStore.kt": STORE_1, f"{PKG}/AuthController.kt": CONTROLLER_1,
                    f"{PKG}/ApiErrors.kt": ERRORS, f"{PKG}/Application.kt": APPLICATION,
                    f"{TPKG}/ApiTest.kt": API_TEST, f"{TPKG}/LoginTest.kt": TEST_LOGIN},
    "AC-auth-002": {f"{PKG}/AccountStore.kt": STORE_2, f"{PKG}/AuthController.kt": CONTROLLER_2,
                    f"{TPKG}/LockoutTest.kt": TEST_LOCKOUT},
    "AC-auth-003": {f"{PKG}/AccountStore.kt": STORE_3, f"{PKG}/AuthController.kt": CONTROLLER_3,
                    f"{TPKG}/SessionTest.kt": TEST_SESSION},
    "AC-auth-004": {f"{PKG}/AccountStore.kt": STORE_4, f"{PKG}/AuthController.kt": CONTROLLER_4,
                    f"{TPKG}/ResetTest.kt": TEST_RESET_4},
    "AC-auth-005": {f"{PKG}/AccountStore.kt": STORE_5, f"{PKG}/AuthController.kt": CONTROLLER_5,
                    f"{TPKG}/ResetTest.kt": TEST_RESET_5},
    "AC-auth-006": {f"{PKG}/AccountStore.kt": STORE_6, f"{TPKG}/StorageTest.kt": TEST_STORAGE},
}

MECHANISMS = {
    "T5": "Gradle JUnit XML (build/test-results)",
    "T6": "Gradle --tests per requirement, JaCoCo XML",
    "T7": "Built-in line mutator; compileTestKotlin check",
    "A5": "OpenAPI generated by springdoc on the running app",
    "A6": "Test base class records each MockMvc response (vendored)",
    "A7": "Spring Boot jar + Schemathesis",
}


def prepare(repo, shared):
    """Nothing to install per copy: Gradle caches dependencies in ~/.gradle."""
