---
name: ai-ocr
description: 直接调用森大集团 ai-exchange 中间件（https://ai-exchange.sunda.com），把图像识别、发票抽取、纯文本总结/抽取等 AI 能力用在当前任务里。当用户提到"识别图片/截图/PDF"、"提取发票字段"、"读图"、"看这张截图"、"图片转文字"、"发票字段抽取"、"合同/单据关键字段抽取"、"表格识别"、"用 OCR"、"调 ai-exchange"、"调 ai-ocr"、"让大模型看这张图"、"总结/抽取/分类文本"、"邮件摘要"、"工单分类"等需求时使用。Skill 内置 API Key，可直接发起 curl 调用并返回结构化结果；遇到 URL 下载失败会自动降级为本地下载 + base64 重传。
---

# ai-ocr：调用 ai-exchange 中间件

把"看图、读票、总结文本"三种 AI 能力暴露给 Claude 直接调用。中间件已经封装好模型路由、提示词、限流、落库，调用方只需要传图片/文本和业务上下文。

## 调用信息（直接可用）

| 项 | 值 |
|---|---|
| Base URL | `https://ai-exchange.sunda.com` |
| API Key | `ext-5558234175a044b5b7a7` |
| 鉴权请求头 | `X-API-Key: ext-5558234175a044b5b7a7` |
| 限流 | 默认 10 秒内最多 5 次，超限返回 429 |
| 同步超时建议 | curl `-m 180` 以上（OCR/发票识别可能耗时 60-120s） |
| 默认模型 | vision = `gemini-3-flash-preview`（OCR/OCR_BILL 都用它）；text = `kimi-k2.5` |

> 这把 Key 是中间件对外联调用 Key，**不要写进任何外部仓库或公开文档**。仅在本 skill 的 curl 示例中硬编码使用。

## 工作流程

1. **判断意图**：按下表选择接口。
2. **准备输入**：图像类接口需要 `image` 对象（URL / base64 二选一）；文本接口需要 `prompt` + `input`。
3. **构造请求**：复制下面对应示例的 curl，替换图片/文本/prompt。
4. **发起调用**：用 Bash 工具执行 curl（同步务必带 `-m 180`）。
5. **解析响应**：
   - `/ocr`、`/text`：优先读 `data.parsedJson`；为 `null` 时回落到 `data.content`。
   - `/ocr-bill`：直接读 `data.invoices[]`。
6. **失败处理**：按 [错误码与降级决策表](#错误码与降级决策表) 处理。`INTERNAL_ERROR` + URL 输入时，**优先尝试本地下载 + base64 重传**。
7. **报告结果**：把识别/抽取出的关键字段以表格或列表呈现给用户；附上 `requestId` 便于回溯。

### 意图 → 接口映射

| 用户想做的事 | 调用接口 | 关键输入 |
|---|---|---|
| 识别图片/PDF 里的文字、表格、合同条款 | `POST /api/v1/exchange/ocr` | `image` + 可选 `prompt` |
| 抽取发票/小票/收据的字段（金额、发票号、销售方等） | `POST /api/v1/exchange/ocr-bill` | `image` + 可选 `context` |
| 总结、分类、抽取纯文本（合同/邮件/工单内容） | `POST /api/v1/exchange/text` | `prompt` + `input` |

## 接口清单

### 1. 通用图像识别 `POST /api/v1/exchange/ocr`

**典型场景**：识别合同截图、表格图片、单据照片、PDF 内容；让模型按指定 JSON schema 返回结构化结果。

#### 方式 A：公网/内网可达的 imageUrl

```bash
curl -sS -m 180 -X POST \
  https://ai-exchange.sunda.com/api/v1/exchange/ocr \
  -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  -H 'Content-Type: application/json' \
  -d '{
    "image": { "imageUrl": "https://example.com/contract.jpg" },
    "prompt": "请识别图中的合同信息，按 JSON 返回：{合同编号, 甲方, 乙方, 金额, 签订日期}"
  }'
```

#### 方式 B：base64（imageUrl 失败时的兜底）

```bash
# Claude 执行时：先在本地 curl/HttpURLConnection 下载到 /tmp/img.bin，再 base64 喂给中间件
B64=$(base64 -w 0 /tmp/img.bin)
cat > /tmp/ocr_req.json <<EOF
{
  "image": { "imageBase64": "$B64", "mimeType": "image/jpeg" },
  "prompt": "请识别图中的合同信息，按 JSON 返回：{合同编号, 甲方, 乙方, 金额, 签订日期}"
}
EOF
curl -sS -m 180 -X POST \
  https://ai-exchange.sunda.com/api/v1/exchange/ocr \
  -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/ocr_req.json
```

> base64 方式请求体大约是原图大小的 1.37 倍；超过 50MB 限制时考虑改异步或裁剪/压缩。

**响应（200）：**

```json
{
  "requestId": "...",
  "status": "SUCCESS",
  "data": {
    "model": "gemini-3-flash-preview",
    "content": "模型原始输出文本（已剥离 markdown 代码块）",
    "parsedJson": { "合同编号": "2026-001", "甲方": "..." },
    "durationMs": 2103
  }
}
```

**`options` 可选字段：**

| 字段 | 类型 | 说明 |
|---|---|---|
| `model` | string | 指定模型，必须在 `/models` 白名单内且类型为 `vision` |
| `responseFormat` | string | `"text"` 或 `"json"`（默认 `json`）；为 `json` 时中间件会尝试解析 `parsedJson`；为 `text` 时 `parsedJson` 始终为 null |
| `temperature` | number | 0-1，采样温度 |
| `maxTokens` | number | 最大输出 token |

> 不传 `prompt` → 走中间件内置默认提示词。
> 传了 `prompt` 但模型没按 JSON 返回 → `content` 是原文，`parsedJson` 为 `null`，此时回落到读 `content`。

### 2. 发票识别 `POST /api/v1/exchange/ocr-bill`

**典型场景**：报销单、差旅票据、采购发票的结构化抽取；支持一图多票；中间件自动落库。

#### 方式 A：imageUrl

```bash
curl -sS -m 180 -X POST \
  https://ai-exchange.sunda.com/api/v1/exchange/ocr-bill \
  -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  -H 'Content-Type: application/json' \
  -d '{
    "businessId": "BX-20260722-001",
    "companyCode": "COMPANY_A",
    "image": { "imageUrl": "https://example.com/invoice.jpg" },
    "context": {
      "businessCategory": "差旅-出租车",
      "amount": 88.50
    }
  }'
```

#### 方式 B：base64 兜底

```bash
B64=$(base64 -w 0 /tmp/invoice.bin)
cat > /tmp/bill_req.json <<EOF
{
  "businessId": "BX-20260722-001",
  "companyCode": "COMPANY_A",
  "image": { "imageBase64": "$B64", "mimeType": "image/jpeg" },
  "context": { "businessCategory": "差旅-出租车", "amount": 88.50 }
}
EOF
curl -sS -m 180 -X POST \
  https://ai-exchange.sunda.com/api/v1/exchange/ocr-bill \
  -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/bill_req.json
```

**响应（200）：**

```json
{
  "requestId": "...",
  "status": "SUCCESS",
  "data": {
    "invoices": [
      {
        "invoiceIndex": 1,
        "invoiceType": "标准发票-打印小票类",
        "invoiceNo": "...",
        "invoiceAmount": 88.50,
        "invoiceCurrency": "CNY",
        "invoiceDate": "2026-01-01",
        "supplier": "销售方公司名",
        "invoiceCompanyName": "销售方公司名（同 supplier）",
        "invoiceTaxNo": "销售方纳税人识别号",
        "buyerCompanyName": "购买方公司名（个人发票/小票为 null）",
        "buyerTaxNo": "购买方纳税人识别号（同上）",
        "aiPersonnel": "购买方个人姓名（仅个人发票）",
        "aiConfidence": 0.92,
        "aiModel": "gemini-3-flash-preview",
        "aiSummary": null
      }
    ],
    "modelDurationMs": 4231
  }
}
```

#### 字段语义（容易踩坑）

- `supplier` = `invoiceCompanyName` = **销售方/开票方**（同义字段，向后兼容）。
- `buyerCompanyName` / `buyerTaxNo` = **购买方公司**，仅公司发票有值。
- `aiPersonnel` = **购买方个人姓名**，仅个人发票有值。
- 同一 `businessId + imageFilename` 重复提交会**覆盖**之前的识别结果。

#### 发票类型 → 字段映射

`invoiceType` 取值与字段填充关系：

| `invoiceType` | `buyerCompanyName` | `buyerTaxNo` | `aiPersonnel` | 典型例子 |
|---|---|---|---|---|
| `标准发票-公司发票` | ✅ 公司名 | ✅ 税号 | `null` | 增值税专用/普通发票（公司） |
| `标准发票-个人发票` | `null` | `null` | ✅ 个人姓名 | 个人代开发票、个人抬头发票 |
| `标准发票-打印小票类` | `null` | `null` | `null`（或个人） | 出租车、餐饮、加油小票 |
| `标准发票-其他` | 视情况 | 视情况 | 视情况 | 不属于以上的标准发票 |
| `手工发票` | 视情况 | 视情况 | 视情况 | 手工填开的发票 |
| `附件` | 通常 `null` | 通常 `null` | 通常 `null` | 报销附件、收据、行程单等 |

> 一图多票 → `invoices[]` 多个元素，`invoiceIndex` 从 1 递增。

### 3. 纯文本总结/抽取 `POST /api/v1/exchange/text`

**典型场景**：总结合同/邮件/工单、抽取关键字段、分类打标。

```bash
curl -sS -m 180 -X POST \
  https://ai-exchange.sunda.com/api/v1/exchange/text \
  -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "请提取合同中的甲方、乙方、金额、签订日期，以 JSON 返回。",
    "input": "甲方：深圳市XX公司。乙方：..."
  }'
```

**`options` 可选字段：** 同 `/ocr`，但 `model` 类型须为 `text`。

**响应结构**与 `/ocr` 一致（`content` + `parsedJson`）。

### 4. 辅助接口

```bash
# 健康检查（无需 Key）
curl -sS https://ai-exchange.sunda.com/api/v1/exchange/health

# 可用模型清单（需要 Key）
curl -sS -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  https://ai-exchange.sunda.com/api/v1/exchange/models

# 查询异步任务结果
curl -sS -H 'X-API-Key: ext-5558234175a044b5b7a7' \
  https://ai-exchange.sunda.com/api/v1/exchange/result/<requestId>
```

## 图像输入规范（`/ocr` 和 `/ocr-bill`）

`image` 字段三种来源任选其一：

| 方式 | 字段 | 中间件行为 | `source_type` 落库 |
|---|---|---|---|
| 公网 URL | `{ "imageUrl": "https://..." }` | 匿名 HTTP GET 下载 | `URL_PUBLIC` |
| 内网 MinIO | `{ "imageUrl": "https://minio-prd.sunda.com/..." }` | 用内置凭据通过 MinIO SDK 下载 | `MINIO_INTERNAL` |
| base64 | `{ "imageBase64": "...", "mimeType": "image/jpeg" }` | 直接解码 | `BASE64` |

支持 MIME：`image/jpeg` / `image/png` / `image/webp` / `application/pdf`。大小上限 50MB。

> **跨域名可达性**：中间件部署环境不一定能访问所有公司内网域名（如 `gfms.sunda.com`、各业务系统域名）。如果 imageUrl 调用失败（典型表现是 `INTERNAL_ERROR` 而非 `INVALID_URL`），改用 **base64 方式**让 Claude 本地下载后重传。

## 调用模式

所有接口默认同步；需要异步时：

| 模式 | 触发条件 | 立即响应 | 获取结果 |
|---|---|---|---|
| 同步（默认） | 不传 `mode` 或 `mode: "SYNC"`，且不传 `callbackUrl` | 200 + 完整结果 | 直接从响应取 |
| 回调 | 传 `callbackUrl`（**注意：不传 mode 也会自动异步**）；可选 `mode: "ASYNC"` | 202 + PENDING | 中间件 POST `callbackUrl`，重试 3 次（30s / 2min / 10min） |
| 轮询 | 传 `mode: "ASYNC"` 但不传 `callbackUrl` | 202 + PENDING | 定时 GET `/result/{requestId}`，建议间隔 3-5s，最多 3 分钟 |

异步任务最长执行 5 分钟，超时状态变 `FAILED`。

## 错误码与降级决策表

### 错误码

| code | HTTP | 触发场景 | 处理建议 |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | Key 无效/未传 | 检查请求头；同 IP 连续 3 次失败会封禁 5 分钟 |
| `RATE_LIMITED` | 429 | 超出限流 | 读 `retryAfterSeconds` 等待后重试 |
| `INVALID_PARAM` | 400 | 参数缺失/格式错 | 检查 `image` / `prompt` / `input` 是否齐全 |
| `INVALID_IMAGE` | 400 | 解码失败/格式不支持 | 确认 MIME 与文件完整 |
| `INVALID_URL` | 400 | URL 格式错或下载失败 | 确认 URL 公网可达或为内网 MinIO |
| `INVALID_MODEL` | 400 | 模型不在白名单 | 调 `/models` 查可用清单 |
| `MODEL_FAILED` | 502 | 模型返回错误或无法解析 | 换模型重试；检查图片质量 |
| `MODEL_TIMEOUT` | 502 | 模型 > 120s 未响应 | 换 flash 系列；PDF 多页改异步 |
| `INTERNAL_ERROR` | 500 | **中间件内部错误，常见于下载环节未捕获异常** | 先尝试 base64 重传；仍失败附 `requestId` 联系管理员 |

错误响应体：

```json
{
  "code": "MODEL_FAILED",
  "message": "...",
  "requestId": "...",
  "retryAfterSeconds": null
}
```

### 降级决策表（按错误自动决策）

| 上一次返回 | 下一步动作 |
|---|---|
| `INTERNAL_ERROR` + 用的是 imageUrl | 改用 base64 重传（用 Bash `curl` 在本地下载 → `base64 -w 0` → 重发） |
| `INTERNAL_ERROR` + 用的是 base64 | 不重试同一方式；报告 `requestId` 给用户，建议联系管理员 |
| `INVALID_URL` | 不要重试同 URL；问用户换一个可达的 URL 或直接提供 base64 |
| `MODEL_TIMEOUT` | 如果是 PDF 多页或大图，改异步；否则换 flash 模型 |
| `MODEL_FAILED` | 调 `/models` 看健康状态；换可用模型重试 |
| `RATE_LIMITED` | 读 `retryAfterSeconds` 等待后重试，不要立即重发 |
| `INVALID_MODEL` | 调 `/models` 拿到正确模型名后重试 |
| `UNAUTHORIZED` | 不要重试；告知用户 Key 可能失效 |

## 常见场景速查

| 场景 | 推荐接口 | 关键 prompt/字段 |
|---|---|---|
| 把合同截图转结构化 JSON | `/ocr` | prompt 里给 JSON schema |
| 识别整页表格 | `/ocr` | prompt 显式说"返回 headers + rows" |
| 报销单发票抽取（一图多票） | `/ocr-bill` | 传 `businessId` + `context` |
| 区分个人/公司发票 | `/ocr-bill` | 看 `invoiceType` + `buyerCompanyName` + `aiPersonnel` 组合判断 |
| 长邮件摘要 | `/text` | prompt = "一句话总结核心结论" |
| 工单分类打标 | `/text` | prompt 指定类别枚举 |
| PDF 多页识别（>30s） | 异步模式 | 用 `callbackUrl` 或轮询 |
| imageUrl 报错 | 改用 base64 | 见 [降级决策表](#降级决策表按错误自动决策) |

## Prompt 模板速查

以下模板按场景复制即用，把 `<...>` 占位符替换为实际值。

### 发票字段抽取（自定义字段）

```
请识别这张发票，按 JSON 返回以下字段，无法识别的填 null：
{发票类型, 发票号码, 开票日期, 销售方名称, 销售方税号, 购买方名称, 购买方税号, 金额, 税额, 价税合计, 备注信息}
只返回 JSON，不要解释。
```

### 合同关键字段抽取

```
请从这张合同图中提取以下信息，按 JSON 返回：
{合同编号, 甲方名称, 乙方名称, 合同金额, 币种, 签订日期, 生效日期, 履约期限, 违约责任摘要, 关键条款列表}
只返回 JSON，不要解释。
```

### 表格识别

```
请把图中的表格转为结构化 JSON：
{
  "headers": [列名数组],
  "rows": [[每行值数组，顺序与 headers 对应]],
  "notes": "表格备注/合并单元格说明，没有则 null"
}
只返回 JSON，不要解释。
```

### 单据/邮件分类

```
请判断这段文本属于以下哪个类别，按 JSON 返回：
{category: "投诉|咨询|报修|结算|表扬|其他", confidence: 0-1, reason: "30字内说明判断依据"}
可选类别说明：
- 投诉：对服务或产品不满
- 咨询：询问业务问题
- 报修：请求维修
- 结算：对账/开票/付款
- 表扬：称赞某项服务
- 其他：不属于以上类别
只返回 JSON，不要解释。
```

### 长文本摘要

```
请用一句话（≤80字）总结以下文本的核心结论，并提取 3-5 个关键词。按 JSON 返回：
{summary: string, keywords: [string], sentiment: "正向|中性|负向"}
只返回 JSON，不要解释。
```

### 报销单合规性预审

```
请识别这张发票并判断是否合规，按 JSON 返回：
{
  invoiceNo, invoiceDate, amount, seller,
  compliant: true/false,
  issues: ["问题描述数组，如 发票抬头与报销人不一致 / 金额超过限值 / 日期早于半年前"],
  riskLevel: "低|中|高"
}
合规标准：
- 发票抬头需清晰可辨
- 金额、日期、发票号字段无缺失
- 不存在明显涂改
只返回 JSON，不要解释。
```

## 调用前自检

- URL 是否正确（base 是 `https://ai-exchange.sunda.com`，无端口）？
- 是否带 `X-API-Key` 请求头？
- 同步 curl 是否设置了 `-m 180` 及以上？
- `/ocr-bill` 的 `businessId` 和 `imageFilename` 是否在**顶层**而不是 `image` 内？
- 用户给的图片 URL 是否公网可达 / 公司 MinIO / 中间件部署环境能访问到？跨公司域名建议直接用 base64。
- 大文件（>10MB）或 PDF 多页 → 是否考虑异步？
- 解析响应时是否优先用 `parsedJson`，回落到 `content`？
- 是否需要传 `options.responseFormat`？（默认 `json`，纯文本场景可设 `text` 避免 JSON 解析告警）

## 参考

完整字段定义、Java/Python 调用示例、变更记录见仓库内 `docs/接入手册.md`。中间件设计方案见 `discuss/ai-exchange中间件改造方案.md`。
