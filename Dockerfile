FROM python:3.12-slim

WORKDIR /app

# Install build tools for some Python packages
RUN apt-get update && apt-get install -y gcc libffi-dev libssl-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers","1","--threads","1", "--timeout", "3600","--graceful-timeout", "3600", "run:app"]

