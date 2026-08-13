FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --create-home app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
RUN mkdir -p /app/outputs && chown -R app:app /app/outputs

USER app

EXPOSE 8000

CMD ["uvicorn", "agent_rfq_extractor.api:app", "--host", "0.0.0.0", "--port", "8000"]
