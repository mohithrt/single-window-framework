# Production deployment: Vercel frontend + FastAPI service

The Vite frontend is deployed to Vercel. The FastAPI API and its SLA worker run on a separate container service with Tesseract and persistent disk support. PostgreSQL must be a managed, publicly reachable database. Uploaded application documents and inspection photos must live on persistent storage; the API's `UPLOAD_DIR` cannot point to a Vercel Function filesystem.

## 1. Deploy the API service

Set the API service build context/root directory to `backend` and use `Dockerfile.production`. Configure the API service to listen on its assigned `PORT`. Attach a persistent volume and set `UPLOAD_DIR` to its mounted directory, for example `/var/lib/mahaclear/uploads`.

Set these server-side environment variables on the API service:

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Managed PostgreSQL URL using the `postgresql+psycopg://` SQLAlchemy scheme |
| `SECRET_KEY` | Unique random secret, at least 32 characters |
| `FRONTEND_ORIGINS` | Exact production Vercel origin, e.g. `https://mahaclear.example` (comma-separated if using multiple approved origins) |
| `UPLOAD_DIR` | Directory on the attached persistent volume |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Desired token lifetime; default is 60 |
| `LLM_API_KEY` | Optional; only if enabling a real LLM provider |

Do not set `DEMO_PASSWORD` for production and do not run either demo seed command against the production database. Configure a database backup and restrict database network access to the API service where your provider allows it.

Before starting or switching the API release, run the migration command once as a release step from the backend working directory:

```sh
alembic upgrade head
```

Initialize only the production role records (no demo accounts or fixture data):

```sh
python -m app.seed_roles
```

Create the first administrator interactively so the initial password is not stored in command history:

```sh
python -m app.create_operator --email admin@your-domain.example --full-name "Government Administrator" --role ADMIN
```

Use `--role OFFICER` with `--company-name`, `--department-code`, and `--department-name` to create a departmental officer account. Applicants register through the public registration page.

Run the web service with the production Dockerfile. Run the SLA sweep as a **separate always-on worker** using the same image, environment, and database:

```sh
python -m app.sla_worker
```

Do not run the development Dockerfile in production: it seeds demo accounts and enables Uvicorn reload.

## 2. Deploy the frontend to Vercel

Create a Vercel project connected to this Git repository and set its **Root Directory** to `frontend`. Vercel reads `frontend/vercel.json`, installs with `npm ci`, builds with `npm run build`, and serves `dist` with SPA route fallback.

Set this Vercel environment variable for **Production, Preview, and Development** as appropriate:

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | API origin only, such as `https://mahaclear-api.example.com` (no trailing slash and no `/api`) |

The frontend sends browser requests directly to that API origin, including document uploads up to the API's existing 15 MB limit. The API's `FRONTEND_ORIGINS` must include the exact Vercel origin used by that deployment. For preview deployments, either add the specific preview origin or disable real-data access there; do not broadly allow `https://*.vercel.app` for an API containing real applicant data.

After adding or changing a Vercel environment variable, create a new deployment so the Vite build embeds the new API origin.

## 3. Verify the release

1. Open `https://<api-host>/health` and confirm it returns `{"status":"ok","service":"mahaclear-ai-api"}`.
2. Open the Vercel site's `/login`, `/register`, and `/applicant` paths directly to confirm SPA routing works.
3. Register a non-demo account, log in, and confirm the browser can reach the API without CORS errors.
4. Upload, download, and replace a test document; restart the API service and confirm the file remains available.
5. Confirm the SLA worker is running and that production contains no demo users or fixture applications.

The deployment cannot be completed until the Vercel project, API host, PostgreSQL database, and persistent file volume have been provisioned and their secrets/origins configured.

## Security gate for real applicant documents

The current prototype keeps bearer access tokens in browser `localStorage`. The Vercel headers add defense in depth, but this token storage should be migrated to Secure, HttpOnly cookies or the government identity provider before using real sensitive applicant documents. Use only synthetic/demo data until that hardening and an application security review are complete.
