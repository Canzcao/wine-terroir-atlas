# 参与贡献

感谢你对风土图鉴的兴趣。这个项目的核心价值在于**数据口径的可信度**，所以贡献门槛主要在「来源」而非「数量」。

## 最重要的三条规则

### 1. 每个实体必须有可追溯的来源

任何写入 `data/catalog-seed.json` 的实体，`data` 里必须有：

```
sourceTitle  — 来源名称（机构/页面标题）
sourceURL    — 合法 http/https URL
checkedDate  — 你核对这个事实的日期（YYYY-MM-DD）
```

`node scripts/validate-data.mjs` 会强制检查，缺一个直接失败。

### 2. 未知就留空，不要推断

- 没有证据的坐标 → `null`（**绝不用「地图视口中心」「公司总部」「产区中心」当酒庄坐标**）
- 没有证据的品种/产量/产权 → `null` 并标注
- 不用相邻产区的数据填充

留空是诚实的；猜测是有害的。

### 3. 边界只用官方公布的图形

- ✅ 法定机构（INAO / EU eAmbrosia / AVA 官方）公布的几何
- ❌ 「把几个点位连起来」「用行政区反推」「用视口框」
- 官方只给行政界时：`boundaryType` 用 `administrative_fallback`，并在 `note` 里**明确写出它不是法定范围**

## 提交前自检

```bash
node scripts/validate-data.mjs     # 数据关联 + 来源字段
node scripts/validate-reports.mjs  # 简报
npm test                           # 授权 / 并发 / 审核 / 文件访问
npm run build                      # 构建必须成功
```

四项全过再提 PR。

## 数据字段速查

提交 `region` 时最少要：

```json
{
  "id": "your-region-id",          // 稳定、唯一、kebab-case
  "kind": "region",
  "name": "中文名",
  "data": {
    "name": "中文名",
    "en": "English / Local Name",
    "country": "国家（中文）",
    "regionId": "父级 id 或 null",   // 层级靠这个指针
    "geoZone": "地理分区（可选）",
    "sourceTitle": "来源",
    "sourceURL": "https://...",
    "checkedDate": "2026-09-29"
  }
}
```

`regionId` 指向的父级**必须已存在**，否则校验失败。

## 代码风格

- 无构建步骤的前端（原生 ES module + Leaflet），不引入打包器
- 脚本用 Node ESM（`.mjs`）或 Python 3（`work/` 下的导入器）
- 注释写「为什么」不写「做什么」
- 中文字符串是项目的一部分（这是中文优先的产品）

## 报告问题

- **数据错误**（边界错了 / 来源失效）：请附上你的独立来源
- **图片侵权**：本项目不含图片；若你的图片出现在上游数据源里，请联系对应来源
- **功能建议**：说明使用场景即可

## 许可

提交即表示你同意你的代码以 MIT、数据以 CC BY 4.0 授权。
