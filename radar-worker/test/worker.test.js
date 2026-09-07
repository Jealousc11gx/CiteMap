import test from "node:test";
import assert from "node:assert/strict";

import worker from "../src/index.js";

function healthyDb() {
  return {
    prepare(sql) {
      assert.equal(sql, "SELECT 1 AS ok");
      return { first: async () => ({ ok: 1 }) };
    },
  };
}

test("health rejects a Worker without RADAR_TOKEN", async () => {
  const response = await worker.fetch(new Request("https://radar.example/health"), {
    DB: healthyDb(),
  });

  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), {
    ok: false,
    error: "RADAR_TOKEN is not configured",
  });
});

test("health verifies token configuration and D1 binding", async () => {
  const response = await worker.fetch(new Request("https://radar.example/health"), {
    RADAR_TOKEN: "secret",
    DB: healthyDb(),
  });

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    ok: true,
    service: "citemap-radar",
  });
});

test("protected endpoints require the bearer token", async () => {
  const response = await worker.fetch(new Request("https://radar.example/profiles"), {
    RADAR_TOKEN: "secret",
    DB: healthyDb(),
  });

  assert.equal(response.status, 401);
  assert.deepEqual(await response.json(), { error: "unauthorized" });
});
