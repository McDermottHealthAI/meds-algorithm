const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");

const html = fs.readFileSync(path.join(__dirname, "../../redirects/index.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

test("old Pages links retain their path, query and fragment on the fixed Read the Docs origin", () => {
  for (const [pathname, suffix] of [
    ["/meds-algorithm/", ""],
    ["/meds-algorithm/index.html", ""],
    ["/meds-algorithm/implemented-algorithms/", "implemented-algorithms/"],
    ["/meds-algorithm/reference/architecture.html", "reference/architecture/"],
    ["/meds-algorithm/reference/architecture/index.html", "reference/architecture/"],
    ["/meds-algorithm//evil.test/", "/evil.test/"],
  ]) {
    let redirected;
    const link = {};
    const location = {pathname, search: "?q=abc", hash: "#profile-classes", replace(value) { redirected = value; }};
    vm.runInNewContext(script, {location, document: {getElementById() { return link; }}});
    const expected = "https://meds-algorithm.readthedocs.io/en/latest/" + suffix + "?q=abc#profile-classes";
    assert.equal(redirected, expected);
    assert.equal(link.href, expected);
    assert.equal(new URL(redirected).hostname, "meds-algorithm.readthedocs.io");
  }
});

test("redirect pages retain a usable link without JavaScript", () => {
  assert(html.includes('href="https://meds-algorithm.readthedocs.io/en/latest/"'));
});

test("old core hosting section links follow the relocated maintenance page", () => {
  let redirected;
  const location = {
    pathname: "/meds-algorithm/", search: "", hash: "#read-the-docs-hosting",
    replace(value) { redirected = value; }
  };
  vm.runInNewContext(script, {location, document: {getElementById() { return {}; }}});
  assert.equal(redirected, "https://meds-algorithm.readthedocs.io/en/latest/documentation/#hosting-and-old-links");
});
