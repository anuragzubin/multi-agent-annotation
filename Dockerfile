FROM python:3.12-slim
WORKDIR /app
COPY server.py ./
COPY static ./static
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
USER 65534:65534
EXPOSE 8000
CMD ["python", "server.py"]
