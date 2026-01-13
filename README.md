# Policy Discovery & Extraction System

## Quick Setup

### 1. Prerequisites
- Docker & Docker Compose
- Ollama (running locally with `qwen3-vl:4b` pulled)

### 2. Start Services
Run the following in your terminal:
```bash
docker-compose up -d --build
```

### 3. Import Workflows (One-Time)

**Option A: Manual Import (Recommended)**
1. Open n8n at http://localhost:5678 and set up your owner account.
2. Click **"Add workflow"** (top right) -> **"Import from..."** -> **"Select File"**.
3. Select `n8n/policy_processing_workflow.json`.
4. Repeat for `n8n/chat_workflow.json`.
5. Ensure both workflows are set to **Active** (toggle switch).


## Configuration

**LLM Model**:
- By default, the system uses your local **Ollama** (`qwen3-vl:4b`).
- To use **Hugging Face** (faster/better coverage), add your token to `docker-compose.yml`:
  ```yaml
  HUGGINGFACEHUB_API_TOKEN=hf_...
  ```

## Usage

| Component | URL | Description |
|-----------|-----|-------------|
| **Chat UI** | [http://localhost:8080](http://localhost:8080) | Ask questions about processed policies. |
| **n8n** | [http://localhost:5678](http://localhost:5678) | Orchestration. Run **"Workflow 1"** to process data. |
| **Qdrant** | [http://localhost:6333](http://localhost:6333) | Vector Database dashboard. |
| **DB** | Port `5432` | PostgreSQL (`user`/`password`/`policy_db`). |

## How to Run Extraction
1. Open n8n at http://localhost:5678.
2. Open **"Workflow 1: Batch Processing"**.
3. Click **Execute Workflow**.
4. This will:
   - Import `List 1.csv`.
   - Crawl & Scrape policies.
   - Extract data using the LLM.
   - Populate the SQL Database and Vector Store.

