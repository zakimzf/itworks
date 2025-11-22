FROM python:3.9-slim

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV FT_APP_ENV="docker"

WORKDIR /binance-pump-alerts

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Fix line endings and make entrypoint executable
RUN apt-get update && apt-get install -y dos2unix && dos2unix entrypoint.sh && chmod +x entrypoint.sh && apt-get remove -y dos2unix && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["./entrypoint.sh", "python", "pumpAlerts.py"]
