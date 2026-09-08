FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .
COPY .env .env 2>/dev/null || true

# Run bot
CMD ["python", "main.py"]
