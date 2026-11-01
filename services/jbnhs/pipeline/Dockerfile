FROM python:3.11
WORKDIR /app

COPY . /app

RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends tesseract-ocr fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir \
    -r requirements.txt \
    -r services/jbnhs/pipeline/requirements.txt
