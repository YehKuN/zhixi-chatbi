import { describe, expect, it } from "vitest";

import { rowsToCsv, safeFilename, tableToCsv, todayStamp } from "@/lib/dataExport";

describe("dataExport", () => {
  it("序列化普通行并保持列顺序", () => {
    expect(rowsToCsv([["月份", "会话数"], ["1月", 120]])).toBe("月份,会话数\r\n1月,120");
  });

  it("按 RFC 4180 转义逗号、引号与换行", () => {
    expect(rowsToCsv([["a,b", 'say "hi"', "line1\nline2"]])).toBe('"a,b","say ""hi""","line1\nline2"');
  });

  it("把空值写成空单元格", () => {
    expect(rowsToCsv([[null, undefined, 0, false]])).toBe(",,0,false");
  });

  it("导出表格时包含表头", () => {
    const csv = tableToCsv({ columns: ["分组", "占比"], rows: [["类型 1", "19.9%"]], row_count: 1 });
    expect(csv).toBe("分组,占比\r\n类型 1,19.9%");
  });

  it("清理文件名中的非法字符", () => {
    expect(safeFilename("UCI/在线:商店*?")).toBe("UCI-在线-商店-");
    expect(safeFilename("  普通 名称  ")).toBe("普通 名称");
  });

  it("日期戳为 8 位数字", () => {
    expect(todayStamp()).toMatch(/^\d{8}$/);
  });
});
