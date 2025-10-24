FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for packages with C extensions
RUN apt-get update && apt-get install -y \
    gcc \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Cloud Run expects PORT environment variable
ENV PORT 8080
EXPOSE 8080

# Use Gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "run:app"]
