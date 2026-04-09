# LLM Extraction Service — Project Knowledge Base v5

## Project Overview

Internal FastAPI service for **Public Bank**. Accepts `.txt` or `.pdf` files, sends text to an LLM microservice (Qwen2.5-VL-7B quantized Q8), and extracts structured data. Two features: **customer detail extraction** and **bank statement summary**.

- Runs on **offline/intranet** — no internet access. All frontend assets must be self-contained.
- Server always started with `python run.py` (not uvicorn directly). Runs on port 8503.
- JavaScript written in **ES5** — no arrow functions, no `?.`, no `??`, `.then/.catch` only. Required for older bank PC browsers.

---

## File Structure

```
project/
├── app/
│   ├── main.py
│   ├── core/config.py
│   ├── features/
│   │   ├── extraction/
│   │   │   ├── prompt.py        build_extraction_prompt()
│   │   │   └── router.py        /extract routes
│   │   └── summary/
│   │       ├── prompt.py        build_summary_prompt()
│   │       └── router.py        /summarise routes
│   ├── models/schemas.py
│   ├── routes/extract.py        backwards compat shim only
│   ├── services/
│   │   ├── docling_client.py    PDF OCR client (pending network access)
│   │   ├── file_service.py
│   │   ├── llm_client.py
│   │   └── prompt_service.py    backwards compat shim only
│   ├── static/
│   │   ├── app.js
│   │   └── style.css
│   └── templates/index.html
├── run.py
└── .env
```

---

## Request Flow

### Customer Detail Extraction
`POST /extract/from-file` → validate file → if PDF: Docling OCR → if txt: decode → build prompt → LLM call → parse JSON → return `ExtractResponse`

### Bank Statement Summary
`POST /summarise/from-file` → validate file → decode txt → build prompt → LLM call → parse JSON → return `SummaryResponse`

---

## LLM Microservice

- **Model:** Qwen2.5-VL-7B-Instruct-UD-Q8_K_XL.gguf
- **Request body:** `{ "prompt": "...", "model": "...", "helper_id": "..." }`
- **Response shape:**
```json
{
  "id": "gen-...",
  "model": "Qwen2.5-VL-7B-Instruct...",
  "created": 1775400000,
  "text": "...(JSON, possibly with explanation text around it)...",
  "finish_reason": "stop",
  "usage": {}
}
```

### Known Qwen2.5 output quirks — all handled by `_normalize_llm_output()`
| Quirk | How handled |
|---|---|
| Adds explanation text before/after JSON | Brace-depth extraction takes last `{...}` block |
| Wraps output in ` ```json``` ` fences | Strategy 1 regex extracts from inside fences |
| Duplicates the JSON output twice | Taking last block gives the correct result |
| Response is slow (30–60s for summary) | Normal for 7B quantized model — not a code issue |

---

## Docling OCR Service

- Converts PDF → markdown text, then passed to LLM
- **Status:** Pending — blocked by bank firewall until deployed to OpenShift. Use `.txt` for now.
- **Property name:** `settings.docling_ocr_url` (not `docling_url`)
- On first successful call, check `logger.debug("Raw Docling response: %s", ...)` to confirm correct key path in `_parse_docling_response()`

---

## Current Code — All Files
- Check the github repo attached.

---

## Pending / Next Steps

- **Tampering detection** — senior requested LLM-based tampering check on bank statement (flag + confidence level + reason). Design: separate second LLM call using `asyncio.gather()` alongside the summary call. Needs `TamperingResult` schema and `build_tampering_prompt()`. **On hold — implement after summary is confirmed working.**
- **PDF support** — coded but inactive. Blocked by bank firewall until OpenShift deployment.
- **Summary end-to-end test** — not yet tested. Need to confirm `_normalize_llm_output` Strategy 2 handles the nested `daily_summaries` / `monthly_summaries` arrays correctly. Still don't get any response from the LLM due to timeout when testing. I tried uploading only 6 transaction rows of bank statement to LLM to make the prompt shorter, but still got timeout issues. 

---

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `Failed to parse LLM response` | No `{...}` block found in LLM text | Check raw debug log — model may have returned no JSON |
| `LLM microservice timed out` | Slow model response | Normal for summary — have tried shortening the prompt and shortening the bank statement rows but still got timeout issues. sometimes on the customer details extraction, the response do not just return the JSON object only but also explanation and duplication of JSON, so this might happen to summary part as well that causing the response slow |
| `502 Bad Gateway` on PDF | Docling unreachable | Expected — use `.txt` until OpenShift deployment |