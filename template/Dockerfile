# Build from the repo root: docker build -f template/Dockerfile -t lead-bot .
FROM python:3.12-slim
RUN pip install --no-cache-dir "aiogram>=3.31" pyyaml python-dotenv
WORKDIR /app
COPY template ./template
CMD ["python", "-m", "template.bot"]
