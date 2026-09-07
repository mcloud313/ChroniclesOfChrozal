FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home chrozal
COPY . .
RUN mkdir -p /app/logs && chown chrozal:chrozal /app/logs
USER chrozal
EXPOSE 8000
CMD ["python", "server.py"]
