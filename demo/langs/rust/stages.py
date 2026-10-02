"""Rust demo: axum 0.8 service, integration tests through tower's oneshot, nextest JUnit, cargo-llvm-cov LCOV."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..common import aqv_config, d

NAME = "Rust"
STACK = "Rust 1.97 · axum 0.8 · tokio · cargo-nextest · cargo-llvm-cov"
JOBS = 1  # copies share one build folder; cargo serializes builds anyway

T = 'target'  # nextest keeps its store (and JUnit) in the repo's target/, even with CARGO_TARGET_DIR set

AQV_CONFIG = aqv_config(["src/"], ["tests/"], d("""
    # Runner profile: how to run the tests and where the reports go.
    runner:
      test: "rm -f %(t)s/nextest/ci/junit.xml; cargo nextest run --profile ci --no-fail-fast {extra} {filter}; code=$?; cp %(t)s/nextest/ci/junit.xml {junit} 2>/dev/null; exit $code"
      coverage: "cargo llvm-cov nextest --lcov --output-path {lcov} --no-fail-fast {filter}"
      filter: "-E 'test(/{id_underscore}/)'"
      select_nothing: "-E 'test(=aqv_selects_no_tests)' --no-tests=pass"
      comment_prefix: ["//", "/*", "*"]

    api:
      # axum can't list its routes, so A5 reads them from the source: a declared, partial check.
      routes_scan:
        files: ["src/**/*.rs"]
        route: '\\.route\\(\\s*"([^"]+)"'
        methods: '\\b(get|post|put|delete|patch)\\s*\\('
      serve: "PORT={port} cargo run -q --bin auth-service"
      serve_timeout: 600
      capture: true

    mutation:
      family: c
      invalid_exit_codes: [101]   # nextest: the build failed, so the mutant doesn't count
      min_kill_ratio: 0.6
      max_mutants: 10
""" % {"t": T}), size_exclude=("Cargo.lock",))

CARGO_TOML = d('''
    [package]
    name = "auth-service"
    version = "0.1.0"
    edition = "2021"

    [dependencies]
    axum = "0.8"
    tokio = { version = "1", features = ["macros", "rt-multi-thread", "net"] }
    tower-http = { version = "0.6", features = ["catch-panic"] }
    serde = { version = "1", features = ["derive"] }
    serde_json = "1"
    rand = "0.8"
    sha2 = "0.10"
    hex = "0.4"

    [dev-dependencies]
    tower = { version = "0.5", features = ["util"] }
''')

NEXTEST = d('''
    [profile.ci]
    fail-fast = false

    [profile.ci.junit]
    path = "junit.xml"
''')

# A6 adapter, vendored by the human: the test helper calls aqv_capture::record after each request.
CAPTURE = d('''
    //! A6 adapter for the Agent Quality Verifier. Test helpers call `record` after each
    //! request; when AQV_CAPTURE_OUT is set it appends the response as one JSON line,
    //! tagged with the running test's name (the test thread's name).
    use std::io::Write;

    pub fn record(method: &str, path: &str, status: u16, body: &serde_json::Value) {
        let Ok(out) = std::env::var("AQV_CAPTURE_OUT") else {
            return;
        };
        let test = std::thread::current().name().unwrap_or("").to_string();
        let line = serde_json::json!({"test": test, "method": method, "path": path, "status": status, "body": body});
        // One write per record: nextest runs tests in parallel processes, and appends of a
        // single write don't interleave.
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(out) {
            let _ = f.write_all(format!("{line}\n").as_bytes());
        }
    }
''')

# ---------------------------------------------------------------------------
# Code, one version per requirement
# ---------------------------------------------------------------------------

LIB = "pub mod api;\npub mod auth;\n"

AUTH_1 = d('''
    //! Accounts and the rules for signing in.
    use std::collections::HashMap;

    use rand::RngCore;

    #[derive(Default)]
    pub struct Store {
        accounts: HashMap<String, String>,
    }

    impl Store {
        pub fn new() -> Self {
            Self::default()
        }

        pub fn with_demo_accounts() -> Self {
            let mut store = Self::new();
            store.add_account("ada@example.com", "correct horse");
            store
        }

        pub fn add_account(&mut self, email: &str, password: &str) {
            self.accounts.insert(email.to_string(), password.to_string());
        }

        pub fn has_account(&self, email: &str) -> bool {
            self.accounts.contains_key(email)
        }

        pub fn sign_in(&mut self, email: &str, password: &str) -> String {
            if self.accounts.get(email).map(String::as_str) == Some(password) {
                return new_token();
            }
            "denied".to_string()
        }
    }

    fn new_token() -> String {
        let mut bytes = [0u8; 16];
        rand::thread_rng().fill_bytes(&mut bytes);
        hex::encode(bytes)
    }
''')

AUTH_2 = (
    AUTH_1.replace("use std::collections::HashMap;\n", "use std::collections::{HashMap, HashSet};\n")
    .replace("use rand::RngCore;\n", "use rand::RngCore;\n\npub const MAX_FAILED_ATTEMPTS: u32 = 3;\n")
    .replace("    accounts: HashMap<String, String>,\n}\n",
             "    accounts: HashMap<String, String>,\n    failed: HashMap<String, u32>,\n    locked: HashSet<String>,\n}\n")
    .replace(
        "    pub fn sign_in(&mut self, email: &str, password: &str) -> String {\n"
        "        if self.accounts.get(email).map(String::as_str) == Some(password) {\n"
        "            return new_token();\n"
        "        }\n",
        "    pub fn sign_in(&mut self, email: &str, password: &str) -> String {\n"
        "        if self.locked.contains(email) {\n"
        '            return "locked".to_string();\n'
        "        }\n"
        "        if self.accounts.get(email).map(String::as_str) == Some(password) {\n"
        "            self.failed.insert(email.to_string(), 0);\n"
        "            return new_token();\n"
        "        }\n"
        "        let failures = self.failed.entry(email.to_string()).or_insert(0);\n"
        "        *failures += 1;\n"
        "        if *failures >= MAX_FAILED_ATTEMPTS {\n"
        "            self.locked.insert(email.to_string());\n"
        "        }\n",
    )
)

AUTH_3 = AUTH_2.replace(
    "pub const MAX_FAILED_ATTEMPTS: u32 = 3;\n",
    "pub const MAX_FAILED_ATTEMPTS: u32 = 3;\npub const SESSION_TTL_SECONDS: i64 = 30 * 60;\n\n"
    "/// Whether a session last seen at `last_seen` has expired at `now` (Unix seconds).\n"
    "pub fn is_expired(last_seen: i64, now: i64) -> bool {\n    now - last_seen > SESSION_TTL_SECONDS\n}\n",
)

AUTH_4 = AUTH_3.replace(
    "    locked: HashSet<String>,\n}\n",
    "    locked: HashSet<String>,\n    pub reset_outbox: Vec<String>,\n}\n",
).replace(
    '        "denied".to_string()\n    }\n}\n',
    '        "denied".to_string()\n    }\n\n'
    "    pub fn request_reset(&mut self, email: &str) -> bool {\n"
    "        if self.accounts.contains_key(email) {\n"
    "            self.reset_outbox.push(email.to_string());\n"
    "            return true;\n"
    "        }\n"
    "        false\n"
    "    }\n}\n",
)

AUTH_5 = AUTH_4.replace(
    "    pub fn request_reset(&mut self, email: &str) -> bool {\n"
    "        if self.accounts.contains_key(email) {\n"
    "            self.reset_outbox.push(email.to_string());\n"
    "            return true;\n"
    "        }\n"
    "        false\n"
    "    }\n",
    "    pub fn request_reset(&mut self, email: &str) {\n"
    "        if self.accounts.contains_key(email) {\n"
    "            self.reset_outbox.push(email.to_string());\n"
    "        }\n"
    "    }\n",
)

AUTH_6 = (
    AUTH_5.replace("use rand::RngCore;\n", "use rand::RngCore;\nuse sha2::{Digest, Sha256};\n")
    .replace("#[derive(Default)]\npub struct Store {\n    accounts: HashMap<String, String>,\n",
             "pub struct Credential {\n    pub salt: String,\n    pub digest: String,\n}\n\n"
             "/// Hex SHA-256 of salt + password.\n"
             "pub fn hash_password(password: &str, salt: &str) -> String {\n"
             "    hex::encode(Sha256::digest(format!(\"{salt}{password}\").as_bytes()))\n}\n\n"
             "#[derive(Default)]\npub struct Store {\n    accounts: HashMap<String, Credential>,\n")
    .replace(
        "    pub fn add_account(&mut self, email: &str, password: &str) {\n"
        "        self.accounts.insert(email.to_string(), password.to_string());\n"
        "    }\n",
        "    pub fn add_account(&mut self, email: &str, password: &str) {\n"
        "        let mut salt = [0u8; 8];\n"
        "        rand::thread_rng().fill_bytes(&mut salt);\n"
        "        let salt = hex::encode(salt);\n"
        "        let digest = hash_password(password, &salt);\n"
        "        self.accounts.insert(email.to_string(), Credential { salt, digest });\n"
        "    }\n\n"
        "    pub fn stored(&self, email: &str) -> Option<&Credential> {\n"
        "        self.accounts.get(email)\n"
        "    }\n\n"
        "    fn password_matches(&self, email: &str, password: &str) -> bool {\n"
        "        self.accounts.get(email).is_some_and(|c| hash_password(password, &c.salt) == c.digest)\n"
        "    }\n",
    )
    .replace("        if self.accounts.get(email).map(String::as_str) == Some(password) {\n",
             "        if self.password_matches(email, password) {\n")
)

API_1 = d('''
    //! HTTP routes for the auth service.
    use std::sync::{Arc, Mutex};

    use axum::{
        extract::{rejection::JsonRejection, State},
        http::StatusCode,
        response::{IntoResponse, Response},
        routing::post,
        Json, Router,
    };
    use serde::Deserialize;
    use serde_json::json;
    use tower_http::catch_panic::CatchPanicLayer;

    use crate::auth::Store;

    pub type SharedStore = Arc<Mutex<Store>>;

    #[derive(Deserialize)]
    struct Credentials {
        email: String,
        password: String,
    }

    fn invalid() -> Response {
        (StatusCode::BAD_REQUEST, Json(json!({"error": "invalid_request"}))).into_response()
    }

    async fn login(State(store): State<SharedStore>, body: Result<Json<Credentials>, JsonRejection>) -> Response {
        let Ok(Json(body)) = body else {
            return invalid();
        };
        let result = store.lock().unwrap().sign_in(&body.email, &body.password);
        if result == "denied" {
            return (StatusCode::UNAUTHORIZED, Json(json!({"error": result}))).into_response();
        }
        Json(json!({"token": result})).into_response()
    }

    pub fn router(store: SharedStore) -> Router {
        Router::new()
            .route("/login", post(login))
            .layer(CatchPanicLayer::new())
            .with_state(store)
    }
''')

API_2 = API_1.replace('    if result == "denied" {\n', '    if result == "denied" || result == "locked" {\n')

API_3 = (
    API_2.replace("use std::sync::{Arc, Mutex};\n", "use std::sync::{Arc, Mutex};\nuse std::time::{SystemTime, UNIX_EPOCH};\n")
    .replace("    extract::{rejection::JsonRejection, State},\n",
             "    extract::{\n        rejection::{JsonRejection, QueryRejection},\n        Query, State,\n    },\n")
    .replace("    routing::post,\n", "    routing::{get, post},\n")
    .replace("use crate::auth::Store;\n", "use crate::auth::{is_expired, Store};\n")
    .replace(
        "pub fn router(store: SharedStore) -> Router {\n",
        "#[derive(Deserialize)]\nstruct SessionQuery {\n    last_seen: i64,\n}\n\n"
        "async fn session(query: Result<Query<SessionQuery>, QueryRejection>) -> Response {\n"
        "    let Ok(Query(query)) = query else {\n        return invalid();\n    };\n"
        "    if query.last_seen < 0 || query.last_seen > 4102444800 {\n        return invalid();\n    }\n"
        "    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;\n"
        '    Json(json!({"expired": is_expired(query.last_seen, now)})).into_response()\n}\n\n'
        "pub fn router(store: SharedStore) -> Router {\n",
    )
    .replace('        .route("/login", post(login))\n',
             '        .route("/login", post(login))\n        .route("/session", get(session))\n')
)

API_4 = (
    API_3.replace(
        "pub fn router(store: SharedStore) -> Router {\n",
        "#[derive(Deserialize)]\nstruct ResetRequest {\n    email: String,\n}\n\n"
        "async fn password_reset(State(store): State<SharedStore>, body: Result<Json<ResetRequest>, JsonRejection>) -> Response {\n"
        "    let Ok(Json(body)) = body else {\n        return invalid();\n    };\n"
        "    let sent = store.lock().unwrap().request_reset(&body.email);\n"
        '    let status = if sent { "sent" } else { "unknown_email" };\n'
        '    (StatusCode::ACCEPTED, Json(json!({"status": status}))).into_response()\n}\n\n'
        "pub fn router(store: SharedStore) -> Router {\n",
    )
    .replace('        .route("/session", get(session))\n',
             '        .route("/session", get(session))\n        .route("/password-reset", post(password_reset))\n')
)

API_5 = API_4.replace(
    "    let sent = store.lock().unwrap().request_reset(&body.email);\n"
    '    let status = if sent { "sent" } else { "unknown_email" };\n'
    '    (StatusCode::ACCEPTED, Json(json!({"status": status}))).into_response()\n',
    "    store.lock().unwrap().request_reset(&body.email);\n"
    '    (StatusCode::ACCEPTED, Json(json!({"status": "sent"}))).into_response()\n',
)

MAIN = d('''
    use std::sync::{Arc, Mutex};

    use auth_service::{api, auth::Store};

    #[tokio::main]
    async fn main() {
        let port = std::env::var("PORT").unwrap_or_else(|_| "8000".to_string());
        let store = Arc::new(Mutex::new(Store::with_demo_accounts()));
        let listener = tokio::net::TcpListener::bind(format!("127.0.0.1:{port}")).await.unwrap();
        axum::serve(listener, api::router(store)).await.unwrap();
    }
''')

# ---------------------------------------------------------------------------
# Tests: one integration test binary, tests/api/main.rs, with a module per requirement
# ---------------------------------------------------------------------------

MODS = ["common", "login", "lockout", "session", "reset", "storage"]


def test_main(upto):
    return "mod aqv_capture;\n" + "".join(f"mod {m};\n" for m in MODS[:upto])


COMMON = d('''
    use std::sync::{Arc, Mutex};

    use auth_service::{api, auth::Store};
    use axum::{body::Body, http::Request, Router};
    use serde_json::Value;
    use tower::ServiceExt;

    use crate::aqv_capture;

    pub fn setup() -> (Arc<Mutex<Store>>, Router) {
        let store = Arc::new(Mutex::new(Store::with_demo_accounts()));
        (store.clone(), api::router(store))
    }

    pub async fn call(app: &Router, method: &str, path: &str, body: Option<Value>) -> (u16, Value) {
        let mut req = Request::builder().method(method).uri(path);
        let body = match body {
            Some(v) => {
                req = req.header("content-type", "application/json");
                Body::from(v.to_string())
            }
            None => Body::empty(),
        };
        let res = app.clone().oneshot(req.body(body).unwrap()).await.unwrap();
        let status = res.status().as_u16();
        let bytes = axum::body::to_bytes(res.into_body(), usize::MAX).await.unwrap();
        let value: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        aqv_capture::record(method, path, status, &value);
        (status, value)
    }
''')

TEST_LOGIN = d('''
    use serde_json::json;

    use crate::common::{call, setup};

    #[tokio::test]
    async fn ac_auth_001_sign_in_returns_token() {
        let (_, app) = setup();
        let (status, body) = call(&app, "POST", "/login", Some(json!({"email": "ada@example.com", "password": "correct horse"}))).await;
        assert_eq!(status, 200);
        assert_eq!(body["token"].as_str().unwrap().len(), 32);
    }

    #[tokio::test]
    async fn ac_auth_001_wrong_password_is_denied() {
        let (_, app) = setup();
        let (status, body) = call(&app, "POST", "/login", Some(json!({"email": "ada@example.com", "password": "wrong"}))).await;
        assert_eq!(status, 401);
        assert_eq!(body, json!({"error": "denied"}));
    }

    #[tokio::test]
    async fn ac_auth_001_malformed_request_is_rejected() {
        let (_, app) = setup();
        let (status, body) = call(&app, "POST", "/login", Some(json!({"email": "ada@example.com"}))).await;
        assert_eq!(status, 400);
        assert_eq!(body, json!({"error": "invalid_request"}));
    }
''')

TEST_LOCKOUT = d('''
    use axum::Router;
    use serde_json::json;

    use crate::common::{call, setup};

    async fn fail(app: &Router, times: usize) {
        for _ in 0..times {
            call(app, "POST", "/login", Some(json!({"email": "ada@example.com", "password": "wrong"}))).await;
        }
    }

    async fn good(app: &Router) -> (u16, serde_json::Value) {
        call(app, "POST", "/login", Some(json!({"email": "ada@example.com", "password": "correct horse"}))).await
    }

    #[tokio::test]
    async fn ac_auth_002_locks_after_three_failures() {
        let (_, app) = setup();
        fail(&app, 3).await;
        let (status, body) = good(&app).await;
        assert_eq!(status, 401);
        assert_eq!(body, json!({"error": "locked"}));
    }

    #[tokio::test]
    async fn ac_auth_002_two_failures_do_not_lock() {
        let (_, app) = setup();
        fail(&app, 2).await;
        assert_eq!(good(&app).await.0, 200);
    }

    #[tokio::test]
    async fn ac_auth_002_success_resets_the_count() {
        let (_, app) = setup();
        fail(&app, 2).await;
        good(&app).await;
        fail(&app, 2).await;
        assert_eq!(good(&app).await.0, 200);
    }
''')

TEST_SESSION = d('''
    use std::time::{SystemTime, UNIX_EPOCH};

    use auth_service::auth::is_expired;
    use serde_json::json;

    use crate::common::{call, setup};

    fn now() -> i64 {
        SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64
    }

    #[tokio::test]
    async fn ac_auth_003_expired_after_30_minutes() {
        let (_, app) = setup();
        let (status, body) = call(&app, "GET", &format!("/session?last_seen={}", now() - 31 * 60), None).await;
        assert_eq!(status, 200);
        assert_eq!(body, json!({"expired": true}));
    }

    #[tokio::test]
    async fn ac_auth_003_active_within_30_minutes() {
        let (_, app) = setup();
        let (_, body) = call(&app, "GET", &format!("/session?last_seen={}", now() - 29 * 60), None).await;
        assert_eq!(body, json!({"expired": false}));
    }

    #[test]
    fn ac_auth_003_boundary_is_exactly_30_minutes() {
        assert!(!is_expired(0, 30 * 60));
        assert!(is_expired(0, 30 * 60 + 1));
    }

    #[tokio::test]
    async fn ac_auth_003_rejects_bad_last_seen_and_accepts_edges() {
        let (_, app) = setup();
        for bad in ["soon", "-1", "4102444801"] {
            let (status, body) = call(&app, "GET", &format!("/session?last_seen={bad}"), None).await;
            assert_eq!(status, 400, "{bad}");
            assert_eq!(body, json!({"error": "invalid_request"}));
        }
        for edge in ["0", "4102444800"] {
            assert_eq!(call(&app, "GET", &format!("/session?last_seen={edge}"), None).await.0, 200, "{edge}");
        }
    }
''')

TEST_RESET_4 = d('''
    use serde_json::json;

    use crate::common::{call, setup};

    #[tokio::test]
    async fn ac_auth_004_link_sent_for_known_email() {
        let (store, app) = setup();
        let (status, _) = call(&app, "POST", "/password-reset", Some(json!({"email": "ada@example.com"}))).await;
        assert_eq!(status, 202);
        assert_eq!(store.lock().unwrap().reset_outbox, vec!["ada@example.com"]);
    }

    #[tokio::test]
    async fn ac_auth_004_no_link_for_unknown_email() {
        let (store, app) = setup();
        call(&app, "POST", "/password-reset", Some(json!({"email": "nobody@example.com"}))).await;
        assert!(store.lock().unwrap().reset_outbox.is_empty());
    }
''')

TEST_RESET_5 = TEST_RESET_4 + d('''

    #[tokio::test]
    async fn ac_auth_005_same_response_for_unknown_email() {
        let (_, app) = setup();
        let known = call(&app, "POST", "/password-reset", Some(json!({"email": "ada@example.com"}))).await;
        let unknown = call(&app, "POST", "/password-reset", Some(json!({"email": "nobody@example.com"}))).await;
        assert_eq!(known.0, 202);
        assert_eq!(known.1, json!({"status": "sent"}));
        assert_eq!(known, unknown);
    }

    #[tokio::test]
    async fn ac_auth_005_known_email_still_gets_its_link() {
        let (store, app) = setup();
        call(&app, "POST", "/password-reset", Some(json!({"email": "nobody@example.com"}))).await;
        call(&app, "POST", "/password-reset", Some(json!({"email": "ada@example.com"}))).await;
        assert_eq!(store.lock().unwrap().reset_outbox, vec!["ada@example.com"]);
    }
''')

TEST_STORAGE = d('''
    use auth_service::auth::{hash_password, Store};

    #[test]
    fn ac_auth_006_password_not_stored_in_plain_text() {
        let mut store = Store::new();
        store.add_account("bo@example.com", "s3cret");
        let c = store.stored("bo@example.com").unwrap();
        assert_ne!(c.salt, "s3cret");
        assert_ne!(c.digest, "s3cret");
        assert_eq!(c.digest, hash_password("s3cret", &c.salt));
    }

    #[test]
    fn ac_auth_006_hashed_password_still_signs_in() {
        let mut store = Store::new();
        store.add_account("bo@example.com", "s3cret");
        let token = store.sign_in("bo@example.com", "s3cret");
        assert!(token != "denied" && token != "locked");
        assert_eq!(store.sign_in("bo@example.com", "nope"), "denied");
    }

    #[test]
    fn ac_auth_006_same_password_gets_different_salts() {
        let mut store = Store::new();
        store.add_account("a@example.com", "s3cret");
        store.add_account("b@example.com", "s3cret");
        assert_ne!(store.stored("a@example.com").unwrap().salt, store.stored("b@example.com").unwrap().salt);
    }
''')

# ---------------------------------------------------------------------------
# What the builder needs
# ---------------------------------------------------------------------------

GITIGNORE = "/target\n.aqv-out/\n"

_LOCK = {}


def cargo_lock():
    """Cargo.lock for CARGO_TOML, generated once so the scaffold commit is complete."""
    if "lock" not in _LOCK:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Cargo.toml").write_text(CARGO_TOML)
            Path(tmp, "src").mkdir()
            Path(tmp, "src/lib.rs").write_text("")
            subprocess.run(["cargo", "generate-lockfile", "-q"], cwd=tmp, check=True)
            _LOCK["lock"] = Path(tmp, "Cargo.lock").read_text()
    return _LOCK["lock"]


def SCAFFOLD():
    return {"Cargo.toml": CARGO_TOML, "Cargo.lock": cargo_lock(), ".config/nextest.toml": NEXTEST,
            ".aqv.yml": AQV_CONFIG, "tests/api/aqv_capture.rs": CAPTURE, "tests/api/main.rs": "mod aqv_capture;\n"}


CODE = {
    "AC-auth-001": {"src/lib.rs": LIB, "src/auth.rs": AUTH_1, "src/api.rs": API_1, "src/main.rs": MAIN,
                    "tests/api/main.rs": test_main(2), "tests/api/common.rs": COMMON,
                    "tests/api/login.rs": TEST_LOGIN},
    "AC-auth-002": {"src/auth.rs": AUTH_2, "src/api.rs": API_2, "tests/api/main.rs": test_main(3),
                    "tests/api/lockout.rs": TEST_LOCKOUT},
    "AC-auth-003": {"src/auth.rs": AUTH_3, "src/api.rs": API_3, "tests/api/main.rs": test_main(4),
                    "tests/api/session.rs": TEST_SESSION},
    "AC-auth-004": {"src/auth.rs": AUTH_4, "src/api.rs": API_4, "tests/api/main.rs": test_main(5),
                    "tests/api/reset.rs": TEST_RESET_4},
    "AC-auth-005": {"src/auth.rs": AUTH_5, "src/api.rs": API_5, "tests/api/reset.rs": TEST_RESET_5},
    "AC-auth-006": {"src/auth.rs": AUTH_6, "tests/api/main.rs": test_main(6), "tests/api/storage.rs": TEST_STORAGE},
}

MECHANISMS = {
    "T5": "cargo-nextest JUnit",
    "T6": "cargo-llvm-cov + nextest filter per requirement, LCOV",
    "T7": "Built-in line mutator; nextest build-failure exit code",
    "A5": "Source scan of .route(...) calls (partial)",
    "A6": "Test helper records each oneshot response (vendored)",
    "A7": "cargo run + Schemathesis",
}


def env(shared):
    return {"CARGO_TARGET_DIR": str(shared / "target")}


def prepare(repo, shared):
    """Nothing to install per copy: crates download on first build into the shared target."""
