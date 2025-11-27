FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/* || true
RUN python -m pip install --upgrade pip
RUN python -m pip install -r requirements.txt
RUN mkdir -p logs
CMD ["bash","scripts/run_appointment_suite.sh"]
