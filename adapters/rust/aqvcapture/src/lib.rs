//! Records the HTTP responses a test sees, for the Agent Quality Verifier (A6).
//!
//! When `AQV_CAPTURE_OUT` is set, each response is appended to that file as one JSON line, tagged
//! with the running test's name. Otherwise nothing is written, so tests behave the same outside
//! the verifier.

use std::io::Write;

use axum::body::Body;
use axum::http::{HeaderMap, Request, StatusCode};
use axum::Router;
use http_body_util::BodyExt;
use tower::ServiceExt;

/// What the service answered.
#[derive(Debug, Clone)]
pub struct Response {
    pub status: StatusCode,
    pub headers: HeaderMap,
    pub body: Vec<u8>,
}

impl Response {
    /// The body as JSON, or `Null` when it is not JSON.
    pub fn json(&self) -> serde_json::Value {
        serde_json::from_slice(&self.body).unwrap_or(serde_json::Value::Null)
    }

    /// The body as text.
    pub fn text(&self) -> String {
        String::from_utf8_lossy(&self.body).into_owned()
    }
}

/// Sends `request` to `app`, records the response and returns it. Call it from the test function
/// itself, not from a spawned task: the response is tagged with the name of the test's thread.
pub async fn send(app: &Router, request: Request<Body>) -> Response {
    let method = request.method().as_str().to_string();
    let path = request.uri().path().to_string();
    let response = app.clone().oneshot(request).await.expect("the router never fails");
    let (parts, body) = response.into_parts();
    let body = body.collect().await.map(|b| b.to_bytes().to_vec()).unwrap_or_default();
    record(&method, &path, parts.status.as_u16(), &body);
    Response { status: parts.status, headers: parts.headers, body }
}

/// Notes one response, for tests that reach the service some other way than `send`.
pub fn record(method: &str, path: &str, status: u16, body: &[u8]) {
    let Ok(out) = std::env::var("AQV_CAPTURE_OUT") else {
        return;
    };
    let parsed = serde_json::from_slice::<serde_json::Value>(body)
        .unwrap_or_else(|_| serde_json::Value::String(String::from_utf8_lossy(body).into_owned()));
    let line = serde_json::json!({"test": test_name(), "method": method, "path": path, "status": status, "body": parsed});
    // One write per record: nextest runs tests in parallel processes, and appends of a single
    // write don't interleave.
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(out) {
        let _ = f.write_all(format!("{line}\n").as_bytes());
    }
}

/// The running test: the test harness names each test's thread after it.
fn test_name() -> String {
    std::thread::current().name().unwrap_or("").to_string()
}
