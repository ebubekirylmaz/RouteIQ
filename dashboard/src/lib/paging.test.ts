import { describe, expect, it } from "vitest";

import { clampPage, describeRange, pageCount } from "./paging";

describe("pageCount", () => {
  it.each([
    [0, 20, 1],
    [1, 20, 1],
    [20, 20, 1],
    [21, 20, 2],
    [87, 20, 5],
    [100, 20, 5],
  ])("%i rows in pages of %i make %i page(s)", (total, size, expected) => {
    expect(pageCount(total, size)).toBe(expected);
  });
});

describe("clampPage", () => {
  it("keeps a valid page", () => {
    expect(clampPage(2, 87, 20)).toBe(2);
    expect(clampPage(0, 87, 20)).toBe(0);
  });

  it("steps back when the last page has been emptied", () => {
    // 41 rows made 3 pages. After one is resolved, 40 rows make 2 pages and page 2 is gone.
    expect(clampPage(2, 40, 20)).toBe(1);
  });

  it("goes to the first page when nothing is left", () => {
    expect(clampPage(3, 0, 20)).toBe(0);
  });

  it("never goes below the first page", () => {
    expect(clampPage(-1, 87, 20)).toBe(0);
  });
});

describe("describeRange", () => {
  it("describes the rows on a page", () => {
    expect(describeRange(0, 20, 20, 87)).toBe("1-20 of 87");
    expect(describeRange(4, 20, 7, 87)).toBe("81-87 of 87");
  });

  it("describes a single row", () => {
    expect(describeRange(0, 20, 1, 1)).toBe("1-1 of 1");
  });

  it("describes an empty list", () => {
    expect(describeRange(0, 20, 0, 0)).toBe("0 of 0");
  });

  it("describes an empty page of a non-empty list without inventing a range", () => {
    expect(describeRange(3, 20, 0, 41)).toBe("0 of 41");
  });
});
