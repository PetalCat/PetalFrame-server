FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg and any basic build tools
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy app files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
