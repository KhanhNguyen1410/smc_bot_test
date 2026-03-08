FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Ensure data output directory is writable if needed (state.json)
RUN chmod 777 .

# Start the bot
CMD ["python", "main.py"]
