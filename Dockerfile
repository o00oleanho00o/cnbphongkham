FROM python:3.12-alpine

WORKDIR /app

# Copy source once so the container can serve static prototype assets.
COPY . /app

EXPOSE 4173

CMD ["python", "-m", "http.server", "4173", "--bind", "0.0.0.0", "--directory", "/app/prototype"]
