# Rust edits used by the scenarios. Each function changes files only; the scenario commits.

e_impl_007() {
  replace src/auth.rs "    pub fn add_account(&mut self, email: &str, password: &str) {
" "    pub fn add_account(&mut self, email: &str, password: &str) {
        if password.len() < 6 {
            return;
        }
"
}

add_test_module() {  # add_test_module NAME: register tests/api/NAME.rs in the test binary
  printf 'mod %s;\n' "$1" >> tests/api/main.rs
}

e_tests_007() {
  cat > tests/api/password_length.rs <<'RS'
use auth_service::auth::Store;

#[test]
fn ac_auth_007_five_characters_rejected() {
    let mut store = Store::new();
    store.add_account("bo@example.com", "five5");
    assert!(!store.has_account("bo@example.com"));
}

#[test]
fn ac_auth_007_six_characters_accepted() {
    let mut store = Store::new();
    store.add_account("bo@example.com", "six666");
    assert!(store.has_account("bo@example.com"));
}
RS
  add_test_module password_length
}

e_test_007_assert_true() {
  cat > tests/api/password_length.rs <<'RS'
#[test]
fn ac_auth_007_short_passwords_rejected() {
    assert!(true);
}
RS
  add_test_module password_length
}

e_comment_007() {
  replace src/auth.rs "    pub fn add_account(&mut self, email: &str, password: &str) {
" "    pub fn add_account(&mut self, email: &str, password: &str) {
        // TODO: enforce the minimum password length
"
}

e_threshold_4() { replace src/auth.rs "pub const MAX_FAILED_ATTEMPTS: u32 = 3;" "pub const MAX_FAILED_ATTEMPTS: u32 = 4;"; }

e_lockout_gt() { replace src/auth.rs "if *failures >= MAX_FAILED_ATTEMPTS {" "if *failures > MAX_FAILED_ATTEMPTS {"; }

# Renames is_expired in the code but not in its test, so the test binary no longer compiles.
e_rename_expiry_src_only() {
  replace src/auth.rs "pub fn is_expired(" "pub fn session_expired("
  replace src/api.rs "use crate::auth::{is_expired, Store};" "use crate::auth::{session_expired, Store};"
  replace src/api.rs '"expired": is_expired(' '"expired": session_expired('
}

e_weak_lockout_tests() {
  cat > tests/api/lockout.rs <<'RS'
use serde_json::json;

use crate::common::{call, setup};

#[tokio::test]
async fn ac_auth_002_failed_attempts_are_rejected() {
    let (_, app) = setup();
    for _ in 0..3 {
        let (status, _) = call(&app, "POST", "/login", Some(json!({"email": "ada@example.com", "password": "wrong"}))).await;
        assert_eq!(status, 401);
    }
}
RS
}

e_logout_route_and_test() {
  replace src/api.rs "pub fn router(store: SharedStore) -> Router {
" "async fn logout() -> Response {
    Json(json!({\"status\": \"signed_out\"})).into_response()
}

pub fn router(store: SharedStore) -> Router {
"
  replace src/api.rs '        .route("/login", post(login))
' '        .route("/login", post(login))
        .route("/logout", post(logout))
'
  cat > tests/api/logout.rs <<'RS'
use serde_json::json;

use crate::common::{call, setup};

#[tokio::test]
async fn ac_auth_007_sign_out() {
    let (_, app) = setup();
    let (status, body) = call(&app, "POST", "/logout", None).await;
    assert_eq!(status, 200);
    assert_eq!(body, json!({"status": "signed_out"}));
}
RS
  add_test_module logout
}

e_rename_token() {
  replace src/api.rs 'Json(json!({"token": result}))' 'Json(json!({"access_token": result}))'
  replace tests/api/login.rs 'body["token"]' 'body["access_token"]'
}

e_debug_route() {
  replace src/api.rs "pub fn router(store: SharedStore) -> Router {
" "async fn debug_users() -> Response {
    Json(json!({\"users\": [\"ada@example.com\"]})).into_response()
}

pub fn router(store: SharedStore) -> Router {
"
  replace src/api.rs '        .route("/login", post(login))
' '        .route("/login", post(login))
        .route("/debug/users", get(debug_users))
'
}

e_leak_password() {
  replace src/api.rs 'Json(json!({"token": result}))' 'Json(json!({"token": result, "debug_password": body.password}))'
}

e_status_423() {
  replace src/api.rs '        return (StatusCode::UNAUTHORIZED, Json(json!({"error": result}))).into_response();' '        let status = if result == "locked" { StatusCode::LOCKED } else { StatusCode::UNAUTHORIZED };
        return (status, Json(json!({"error": result}))).into_response();'
  replace tests/api/lockout.rs '    assert_eq!(status, 401);
    assert_eq!(body, json!({"error": "locked"}));' '    assert_eq!(status, 423);
    assert_eq!(body, json!({"error": "locked"}));'
}

e_reset_crash() {
  replace src/api.rs "    store.lock().unwrap().request_reset(&body.email);
" "    let _domain = body.email.split('@').nth(1).unwrap().to_lowercase();
    store.lock().unwrap().request_reset(&body.email);
"
}

e_doc_comment() {
  replace src/auth.rs "    pub fn sign_in(&mut self, email: &str, password: &str) -> String {
" "    /// Returns a session token, or \"denied\" / \"locked\".
    pub fn sign_in(&mut self, email: &str, password: &str) -> String {
"
}

e_big_file() {
  python3 - <<'PY'
lines = ["//! Email domains that never receive reset links.", "pub const BLOCKED_DOMAINS: &[&str] = &["]
lines += [f'    "blocked-{i}.example",' for i in range(600)]
lines += ["];"]
open("src/blocked_domains.rs", "w").write("\n".join(lines) + "\n")
PY
  printf 'pub mod blocked_domains;\n' >> src/lib.rs
}
