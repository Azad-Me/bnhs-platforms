FROM python:3.11
WORKDIR /app

COPY . /app

RUN apt-get -qq update & apt-get -qq install -y tesseract-ocr
RUN apt-get -qq install -y fonts-dejavu-core & fc-match DejaVuSans
RUN fc-match DejaVuSans
