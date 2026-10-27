FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY app.py /app/app.py

EXPOSE 8000
CMD ["python3", "app.py"]

