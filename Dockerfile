# Cloud Run ready Dockerfile with fuller font pack
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system fonts and tools, then clean up
RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-dejavu-core \
      fonts-roboto \
      wget \
      ca-certificates \
      fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Fetch Nunito ExtraBold and Baloo2 Bold (ignore errors if URLs change)
RUN mkdir -p /usr/share/fonts/truetype/custom && \
    (wget -O /usr/share/fonts/truetype/custom/Nunito-ExtraBold.ttf \
      https://raw.githubusercontent.com/google/fonts/main/ofl/nunito/static/Nunito-ExtraBold.ttf || true) && \
    (wget -O /usr/share/fonts/truetype/custom/Baloo2-Bold.ttf \
      https://raw.githubusercontent.com/google/fonts/main/ofl/baloo2/Baloo2-Bold.ttf || true) && \
    fc-cache -fv || true

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy app (includes any local assets/fonts)
COPY . /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
