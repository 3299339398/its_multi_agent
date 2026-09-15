FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace

WORKDIR /workspace

COPY backend/app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /workspace/its_multi_agent

EXPOSE 8000
CMD ["uvicorn", "its_multi_agent.backend.app.api.main:create_fast_api", "--factory", "--host", "0.0.0.0", "--port", "8000"]
