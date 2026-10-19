import { test } from "node:test";
import assert from "node:assert/strict";
import { percentile, scaleBox } from "../src/metrics.mjs";
import { Chess } from "chess.js";

test("metrics use percentiles and handle missing samples", () => {
  assert.equal(percentile([], 95), null);
  assert.equal(percentile([100, 2, 3, 4, 5], 50), 4);
  assert.ok(Math.abs(percentile([100, 2, 3, 4, 5], 95) - 81) < 1e-9);
});
test("bbox scales capture coordinates into CSS coordinates", () => {
  assert.deepEqual(
    scaleBox([96, 72, 480, 360], 960, 720, 480, 360),
    [48, 36, 192, 144],
  );
});
test("both sides can move; castling and promotion are supported", () => {
  const game = new Chess();
  game.move({ from: "e2", to: "e4" });
  game.move({ from: "e7", to: "e5" });
  assert.throws(() => game.move({ from: "e4", to: "e6" }));
  game.load("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
  game.move({ from: "e1", to: "g1" });
  assert.equal(game.get("f1").type, "r");
  game.load("7k/P7/8/8/8/8/8/7K w - - 0 1");
  game.move({ from: "a7", to: "a8", promotion: "n" });
  assert.equal(game.get("a8").type, "n");
});
