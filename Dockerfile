FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY policy ./policy
COPY data ./data
COPY tools ./tools
COPY tests ./tests
COPY run.py README.md SETUP.md VERIFICATION.md ./

USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('API_PORT','8080')+'/health',timeout=3)"

CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${API_PORT:-8080}"]
