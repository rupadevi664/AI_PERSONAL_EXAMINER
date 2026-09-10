# Docker Deployment Guide - AI Personal Examiner

This guide explains how to run AI Personal Examiner inside a Docker container locally, or deploy the container to any cloud server / VPS.

---

## 1. Quick Start with Docker Compose (Recommended)

### Prerequisites
1. Ensure your `.env` file is present in the project root with your LLM API key:
   ```bash
   # In .env
   GROQ_API_KEY=your_groq_api_key_here
   # or GEMINI_API_KEY=your_gemini_key
   ```
2. Make sure port 8000 is not blocked by another local instance (e.g. stop any running `uvicorn` processes).

### Launch Container
From the project root, run:
```bash
docker compose up --build -d
```

### View Status & Logs
```bash
# Check running status and health check
docker compose ps

# Follow container logs in real time
docker compose logs -f
```

### Open the Application
Navigate to [http://localhost:8000](http://localhost:8000) in your browser.
- **Home / Exam Setup**: [http://localhost:8000](http://localhost:8000)
- **Live Interview**: [http://localhost:8000/exam](http://localhost:8000/exam)
- **Learner Dashboard**: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)
- **API Docs (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Stop the Container
```bash
docker compose down
```
*(Note: Your SQLite exam history and question memory are preserved safely inside the Docker volume `examiner_data`)*.

---

## 2. Running with Standard Docker CLI (Without Compose)

### Build Image
```bash
docker build -t ai-personal-examiner .
```

### Run Container
```bash
# Create persistent volume for SQLite
docker volume create examiner_data

# Run container with volume mount and environment variables
docker run -d \
  --name ai-personal-examiner \
  -p 8000:8000 \
  --env-file .env \
  -v examiner_data:/app/data \
  --restart unless-stopped \
  ai-personal-examiner
```

---

## 3. If Docker is Not Yet Installed on Your Windows Machine

If running `docker --version` returns an error on your Windows PC:
1. **Download Docker Desktop**: Visit [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/) and download the Windows installer.
2. **Install with WSL2**: Follow the installer prompts and enable the WSL2 backend (recommended by Docker).
3. **Restart your PC** if prompted.
4. **Open Docker Desktop** and wait until the status indicator in the bottom-left shows green ("Engine running").
5. Run `docker compose up --build -d` in your terminal.

---

## 4. Deploying this Docker Container to the Cloud

Because this project includes a self-contained `Dockerfile`:
- **Railway**: Connect your Git repo; Railway will automatically detect the `Dockerfile`, build it, and expose your service.
- **Render**: Create a **Web Service**, select **Docker** as the runtime, and add your environment variables (`GROQ_API_KEY`, etc.).
- **DigitalOcean / AWS / GCP / Any Linux VPS**:
  1. Clone this repository onto your server.
  2. Create your `.env` file.
  3. Run `docker compose up --build -d`.
  4. (Optional) Put Nginx or Caddy in front with SSL.
