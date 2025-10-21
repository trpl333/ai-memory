# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for static files
RUN mkdir -p static

# Expose ports for Flask (5000), FastAPI (8001), and production (8100)
EXPOSE 5000 8001 8100

# Start the FastAPI application on port 8100 (production)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]