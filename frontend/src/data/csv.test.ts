import { describe, expect, it } from "vitest";
import { parseCsv } from "./csv";

describe("parseCsv", () => {
  it("parses escaped quotes, commas, and line breaks inside quoted fields", () => {
    const rows = parseCsv('name,note,value\r\nalpha,"A, B",1\r\nbeta,"said ""yes""\nnext",2\r\n');

    expect(rows).toEqual([
      { name: "alpha", note: "A, B", value: "1" },
      { name: "beta", note: 'said "yes"\nnext', value: "2" },
    ]);
  });

  it("returns an empty collection for an empty document", () => {
    expect(parseCsv("")).toEqual([]);
  });
});
