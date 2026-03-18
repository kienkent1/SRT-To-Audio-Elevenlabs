FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirement files and install dependencies
COPY environment.yml .
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pysrt \
    requests \
    pydub \
    python-dotenv \
    elevenlabs \
    scalar-fastapi \
    python-multipart

# Copy project files
COPY . .

# Create results directory
RUN mkdir -p results

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
