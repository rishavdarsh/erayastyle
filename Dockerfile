FROM python:3.11-slim

# Install system dependencies for html2image (wkhtmltoimage via wkhtmltopdf)
RUN apt-get update && apt-get install -y \
    wkhtmltopdf \
    xauth xvfb libxrender1 libxext6 libjpeg62-turbo libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port",  "8000"]
