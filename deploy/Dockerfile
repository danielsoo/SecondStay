# Public demo image. The build context is assembled by deploy/build.sh: code, the git-ignored data/raw caches
# and the two CoStar kit files the server reads. No .env and no API keys go into the image.
FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir pillow
COPY kit/ /kit/
COPY app/ /app/

ENV COSTAR_KIT_DIR=/kit \
    SECONDSTAY_OFFLINE=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["python", "-m", "secondstay.web"]
