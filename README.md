# TTB Label Verifier

AI-powered alcohol label compliance verification prototype for TTB (Alcohol and Tobacco Tax and Trade Bureau) compliance agents.

## Overview

Agents upload label images alongside application data. The system uses a vision model to extract regulated fields from the label, compares them against the submitted application, and returns a per-field verdict: **pass**, **warning**, or **fail**. Agents can review non-passing fields, confirm them as correct, or log the corrected value — all corrections are appended to an audit log for future benchmark evaluation.

---

## Setup

### 1. Clone & install

```bash
git clone <repo-url>
cd alcohol-label-verifier
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY
```

### 3. Run

```bash
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000)

---

## Usage

### Single label
1. Upload one image → click **Continue**
2. Fill in application data (Government Warning is pre-filled with TTB canonical text)
3. Click **Run Verification**
4. Review results; for any warning/fail fields:
   - Check **"I have reviewed this field and confirm it is correct"** if the label is acceptable
   - Or enter the correct detected value in the text field
5. Click **Submit Review** — corrections are logged to `logs/audit.jsonl`

### Bulk upload
1. Upload multiple images → click **Continue**
2. Upload a CSV with application data (see format below)
3. Click **Run Verification**

#### CSV format

```
filename,brand_name,class_type,abv,net_contents,bottler_name,bottler_address,country_of_origin,government_warning
label_001.jpg,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,...
```

- `filename` must exactly match the uploaded image filename (case-sensitive)
- `country_of_origin` — leave blank for domestic products
- `government_warning` — leave blank to use the TTB canonical text automatically

A sample CSV is provided at `tests/sample_batch.csv`.

---

## Architecture

```
app/
├── main.py                  # FastAPI app, serves frontend
├── api/routes.py            # Endpoints: /verify/single, /verify/batch, /audit
├── core/
│   ├── vision.py            # Abstracted VisionClient (swap backends here)
│   ├── verifier.py          # Extraction + comparison logic
│   ├── constants.py         # TTB canonical values, field classifications
│   └── prompts/
│       ├── registry.py      # Prompt version registry
│       └── v1_extract.txt   # Extraction prompt v1
├── models/
│   ├── label.py             # ApplicationData
│   ├── result.py            # VerificationResult, FieldVerdict
│   └── audit.py             # AgentCorrection, AuditSubmission
├── services/
│   ├── csv_parser.py        # Bulk CSV parsing + validation
│   └── audit_logger.py      # Appends corrections to logs/audit.jsonl
└── static/index.html        # Single-page frontend
```

### Verdict logic

| Status | Meaning |
|--------|---------|
| ✅ pass | Extracted value matches application value within field-type rules |
| ⚠️ warning | Values are close but differ (case, formatting, partial match) — agent reviews |
| ❌ fail | Clear mismatch, missing required field, or government warning does not match |

Field types:
- **Exact match**: `government_warning` — must match both the application value *and* the TTB canonical text
- **Numeric**: `abv`, `net_contents` — numeric values compared; formatting differences produce a warning
- **Fuzzy**: all other fields — case-insensitive comparison; case differences produce a warning, true mismatches produce a fail

### Adding a new vision backend

1. Implement `VisionClient` ABC in `app/core/vision.py`
2. Register it in the `_BACKENDS` dict
3. Set `VISION_BACKEND=your_backend` in `.env`

### Adding a new prompt version

1. Create `app/core/prompts/v2_extract.txt`
2. Register it in `PROMPT_REGISTRY` in `app/core/prompts/registry.py`
3. Pass `prompt_version=v2` in API calls or form submissions

---

## Audit Log

Corrections are appended to `logs/audit.jsonl` — one JSON object per line.

```json
{
  "entry_id": "uuid",
  "session_id": "uuid",
  "image_filename": "label_001.jpg",
  "field": "brand_name",
  "extracted_value": "Old Tom Distillery",
  "application_value": "OLD TOM DISTILLERY",
  "status_shown": "warning",
  "agent_action": "verified_correct",
  "agent_provided_value": null,
  "model_used": "claude-opus-4-5",
  "prompt_version": "v1",
  "timestamp": "2025-05-13T..."
}
```

Load into pandas for eval work: `pd.read_json('logs/audit.jsonl', lines=True)`

---

## Trade-offs & Limitations

| Area | Decision | Production path |
|------|----------|----------------|
| **Audit log storage** | Local `audit.jsonl` file | Replace `audit_logger.py` with a database writer |
| **Agent identity** | Anonymous sessions (UUID per browser session) | Add auth layer; bind session to agent ID |
| **Batch processing** | Sequential API calls | Parallel with rate-limit-aware concurrency (e.g. `asyncio.Semaphore`) |
| **COLA integration** | None — standalone prototype | Separate procurement/authorization process required |
| **Image quality** | Claude handles mild distortion well; severely degraded images may produce null extractions | Add a pre-processing step (deskew, contrast normalisation) |
| **Network firewall** | Requires outbound HTTPS to `api.anthropic.com` | The Anthropic API endpoint must be whitelisted in production |
| **AI determinism** | Same label may produce slightly different extraction on retry | Record `prompt_version` + `model_used` on every result; use audit log to identify unstable fields |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/health` | Liveness check |
| `GET`  | `/api/constants` | TTB canonical values for frontend pre-fill |
| `GET`  | `/api/prompts` | List available prompt versions |
| `POST` | `/api/verify/single` | Verify a single label (multipart form) |
| `POST` | `/api/verify/batch` | Verify multiple labels with CSV (multipart form) |
| `POST` | `/api/audit` | Submit agent corrections |
