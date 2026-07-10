FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --target=/install -r requirements.txt

FROM gcr.io/distroless/python3-debian12
WORKDIR /app
COPY --from=builder /install /usr/lib/python3.11/site-packages
ENV PYTHONPATH=/usr/lib/python3.11/site-packages
COPY app.py ./
USER nonroot
EXPOSE 5001
CMD ["app.py"]
