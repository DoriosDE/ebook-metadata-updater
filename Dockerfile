FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ebook_metadata_updater.py .

ENV DIRECTORY=""
ENV TEMPLATE=""
ENV TITLE=""
ENV DESCRIPTION=""
ENV SUBJECT=""

ENTRYPOINT ["python", "ebook_metadata_updater.py"]