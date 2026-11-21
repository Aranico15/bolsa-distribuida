FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
# El comando se define en docker-compose (nodo, coordinador o dashboard).
CMD ["python", "-m", "sim.nodo", "--help"]
