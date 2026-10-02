// A6 adapter for Node test runners (Jest, Vitest), loaded as a setup file.
// Records every HTTP response a test triggers (method, path, status, JSON body)
// with the current test's name, as JSON lines in $AQV_CAPTURE_OUT.
// Works for anything that answers through http.ServerResponse: supertest, fetch
// against app.listen(), and Fastify's server.
const fs = require("fs");
const http = require("http");

const out = process.env.AQV_CAPTURE_OUT;
if (out) {
  const proto = http.ServerResponse.prototype;
  // Test files run one after another in a worker, each with its own globals, so
  // patch again from the originals every time this file loads.
  proto.__aqvWrite = proto.__aqvWrite || proto.write;
  proto.__aqvEnd = proto.__aqvEnd || proto.end;
  const currentTest = () => {
    try {
      // Jest puts expect on globalThis; Vitest keeps it under a registered symbol.
      const e = globalThis.expect || globalThis[Symbol.for("expect-global")];
      return (e && e.getState && e.getState().currentTestName) || "";
    } catch {
      return "";
    }
  };
  proto.write = function (chunk, ...rest) {
    if (chunk && typeof chunk !== "function") (this.__aqvChunks = this.__aqvChunks || []).push(Buffer.from(chunk));
    return proto.__aqvWrite.call(this, chunk, ...rest);
  };
  proto.end = function (chunk, ...rest) {
    if (chunk && typeof chunk !== "function") (this.__aqvChunks = this.__aqvChunks || []).push(Buffer.from(chunk));
    try {
      const text = Buffer.concat(this.__aqvChunks || []).toString("utf8");
      let body = null;
      try { body = JSON.parse(text); } catch { body = text || null; }
      const req = this.req || {};
      fs.appendFileSync(out, JSON.stringify({
        test: currentTest(), method: req.method, path: req.originalUrl || req.url, status: this.statusCode, body,
      }) + "\n");
    } catch { /* never break the test run */ }
    return proto.__aqvEnd.call(this, chunk, ...rest);
  };
}
