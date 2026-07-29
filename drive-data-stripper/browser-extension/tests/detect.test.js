const test = require("node:test");
const assert = require("node:assert/strict");

global.window = global; // detect.js attaches to `window`, fall back to the test's global object
require("../lib/detect.js");
const D = global.DriveShieldDetect;

test("detects an email", () => {
  const matches = D.detect("contact jane.doe@acme.com now", null, []);
  assert.ok(matches.some((m) => m.label === "email" && m.value === "jane.doe@acme.com"));
});

test("detects an AWS access key", () => {
  const matches = D.detect("key=AKIAABCDEFGHIJKLMNOP rotate it", null, []);
  assert.ok(matches.some((m) => m.label === "aws_access_key"));
});

test("custom terms are case-insensitive", () => {
  const matches = D.detect("Project SkyNet is confidential", null, ["skynet"]);
  assert.ok(matches.some((m) => m.label === "custom_term:skynet" && m.value === "SkyNet"));
});

test("categories filter restricts the scan", () => {
  const matches = D.detect("email jane@acme.com and phone 555-123-4567", ["email"], []);
  assert.ok(matches.length > 0);
  assert.ok(matches.every((m) => m.label === "email"));
});

test("Luhn-valid credit card is detected", () => {
  const matches = D.detect("card 4111111111111111 on file", ["credit_card"], []);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].value, "4111111111111111");
});

test("Luhn-invalid digit run is not flagged as a credit card", () => {
  const matches = D.detect("ref 1234567890123456 processed", ["credit_card"], []);
  assert.deepEqual(matches, []);
});

test("phone matches are medium confidence, email matches are high", () => {
  const phone = D.detect("call 555-123-4567 now", ["phone"], []);
  const email = D.detect("jane@acme.com", ["email"], []);
  assert.ok(phone.every((m) => m.confidence === "medium"));
  assert.ok(email.every((m) => m.confidence === "high"));
});

test("overlapping matches keep the leftmost, longest span", () => {
  const text = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----";
  const matches = D.detect(text, ["private_key_block"], []);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].value, text);
});

test("redact replaces matches with a placeholder", () => {
  const text = "email jane@acme.com now";
  const matches = D.detect(text, ["email"], []);
  const redacted = D.redact(text, matches);
  assert.ok(!redacted.includes("jane@acme.com"));
  assert.ok(redacted.includes("[REDACTED]"));
});

test("scaffold apply/restore round-trips exactly", () => {
  const text = "reach jane@acme.com or john@acme.com for access";
  const matches = D.detect(text, ["email"], []);
  const { text: scaffolded, mapping, nextOffset } = D.applyScaffold(text, matches);
  assert.ok(!scaffolded.includes("jane@acme.com"));
  assert.ok(!scaffolded.includes("john@acme.com"));
  assert.equal(nextOffset, 2);
  assert.equal(D.restore(scaffolded, mapping), text);
});

test("scaffold index offset keeps tokens unique across chunks", () => {
  const a = D.detect("jane@acme.com", ["email"], []);
  const b = D.detect("john@acme.com", ["email"], []);
  const resultA = D.applyScaffold("jane@acme.com", a, 0);
  const resultB = D.applyScaffold("john@acme.com", b, resultA.nextOffset);
  const combined = Object.assign({}, resultA.mapping, resultB.mapping);
  assert.equal(Object.keys(combined).length, 2);
  assert.equal(D.restore(resultA.text, combined), "jane@acme.com");
  assert.equal(D.restore(resultB.text, combined), "john@acme.com");
});

test("findRemainingTokens reports unmapped tokens", () => {
  assert.deepEqual(D.findRemainingTokens("value is [[SCAFFOLD:email:0]] here"), ["[[SCAFFOLD:email:0]]"]);
  assert.deepEqual(D.findRemainingTokens("no tokens here"), []);
});
