
FROM python:3.13.2

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

EXPOSE 8080

# Run main.py
CMD ["python", "run.py"]
