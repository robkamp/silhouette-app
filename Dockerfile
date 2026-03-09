# Gebruik een lichte Python image
FROM python:3.11-slim

# Installeer systeem-afhankelijkheden voor OpenCV en Poppler (voor PDF-conversie)
RUN apt-get update && apt-get install -y libglib2.0-0 libsm6 libxext6 libxrender-dev poppler-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopieer eerst het requirements-bestand en installeer de afhankelijkheden.
# Deze laag wordt alleen opnieuw gebouwd als requirements.txt wijzigt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de applicatiecode.
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]