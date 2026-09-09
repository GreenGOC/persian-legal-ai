# Legal AI Project

This repository contains a Django backend and a React + Vite frontend for a legal-question assistant. The frontend sends requests to the Django API, and the backend returns answers with citations.

## Project structure

- `config/` — Django project settings and routes
- `legal/` — backend application logic, models, retrieval, and RAG pipeline
- `src/` — React frontend source
- `docker-compose.yaml` — local services for PostgreSQL, MinIO, etcd, and Milvus
- `package.json` — frontend scripts and dependencies

## Prerequisites

Before starting the project, install:

- Python 3.11+
- Node.js 18+
- npm
- Docker Desktop (for local services)
- Git

If PowerShell blocks npm scripts on Windows, run commands with execution policy bypass:

```powershell
powershell -ExecutionPolicy Bypass -Command "npm install"
```

## Environment variables

Create a `.env` file in the project root (`django/.env`) with the values required by the app, for example:

```env
POSTGRES_DB=legal_ai
Important: if you received the dataset as compressed archives (for example `.rar` files), extract them into the `django/data/` folder before running the import command. Do NOT commit or push the extracted data to the repository — the project includes a `.gitignore` entry that excludes `django/data/` so large or sensitive data stays local.
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password

MINIO_ROOT_USER=your_minio_user
MINIO_ROOT_PASSWORD=your_minio_password

OPENROUTER_API=your_openrouter_key
OPENROUTER_MODEL=your_model_name
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

These values are read by the Django settings file.

## 1) Start backend dependencies

From the `django` directory, start the required infrastructure services with Docker:

```powershell
docker compose up -d
```

This starts:

- PostgreSQL on `localhost:5432`
- MinIO on `localhost:9000`
- Milvus on `localhost:19530`
- etcd on the internal Docker network

## 2) Install Python dependencies

Create and activate a virtual environment if you use one, then install the project’s Python dependencies from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The file `requirements.txt` is generated from the Python modules and notebook imports used across the project, so it captures the backend runtime packages needed for Django, embeddings, retrieval, and data preprocessing.

If your environment already contains the required packages, skip this step.

## 3) Run database migrations

```powershell
python manage.py migrate
```

## 4) Import legal data into PostgreSQL

The project imports the JSON legal corpus into the database before any retrieval/index work:

```powershell
python manage.py import_json_documents data/json
```

This command reads the JSON files under the `data/json` folder and inserts the legal documents and provisions into PostgreSQL.

## 5) Build the dense retrieval index

After the data is imported, build the retrieval index used by the backend:

```powershell
python manage.py build_dense_index
```

This step creates the dense embedding index for search and retrieval.

## 6) Warm up the reranker model

Before starting the website, run the reranker test once so the CrossEncoder model is downloaded and cached locally:

```powershell
python manage.py test legal.tests.retrieval.test_reranker
```

This downloads the `safora/reranker-xlm-roberta-large` model used by the reranker and prevents the first UI query from failing due to a missing model download.

## 7) Start the Django API

```powershell
python manage.py runserver 0.0.0.0:9876
```

The backend exposes:

- `http://localhost:9876/admin/`
- `http://localhost:9876/api/chat/`

The chat endpoint accepts a JSON body like:

```json
{
  "question": "What does the law say about ... ?"
}
```

## 8) Start the frontend

Open a second terminal, go to the same `django` directory, and run:

```powershell
npm install
npm run dev -- --host 0.0.0.0
```

Then open the Vite URL printed in the terminal, usually:

```text
http://localhost:5173
```

The frontend is configured to proxy `/api` requests to Django at `http://127.0.0.1:9876`.

## Build for production

To create the production bundle:

```powershell
npm run build
```

This generates the `dist/` folder. You can preview it locally with:

```powershell
npm run preview -- --host 0.0.0.0
```

## Frontend-backend connection

The UI makes requests from the React app to `/api/chat/` via the Vite proxy configured in `vite.config.js`:

```js
server: {
  proxy: {
    '/api': 'http://127.0.0.1:9876',
  },
}
```

The Django route is defined in `config/urls.py` as:

```python
path('api/chat/', chat, name='chat')
```

That means the browser calls the frontend URL, but the actual backend call is forwarded to Django automatically during development.

## Common troubleshooting

### `npm` is blocked by PowerShell execution policy

```powershell
powershell -ExecutionPolicy Bypass -Command "npm install"
```

### Django import errors

Make sure you activated the correct virtual environment and installed the required Python packages before running:

```powershell
python manage.py check
```

### Backend returns 503 or fails to answer questions

Verify that:

- PostgreSQL is running
- MinIO and Milvus are running
- the `.env` file contains valid API keys and database settings
- the OpenRouter model configuration is available

## Notes

This project was built as a legal question-answering prototype. The retrieval and answer-generation layers rely on external services and local infrastructure, so a full working setup requires both the database/storage services and the configured API credentials.
