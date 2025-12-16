# Gebruik een officiële Python runtime als parent image 1
FROM python:3.9-slim

# Zet de werkmap in de container
WORKDIR /app

# Kopieer de requirements file eerst (voor betere caching van Docker layers)
COPY requirements.txt .

# Installeer de benodigde packages
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer de rest van de applicatie code
COPY app.py .
COPY dashboard.html .

# Maak poort 5000 beschikbaar voor de buitenwereld
EXPOSE 5000

# Definieer environment variabele voor Flask
ENV FLASK_APP=app.py

# Start de applicatie wanneer de container start
CMD ["python", "app.py reset-pass"]
