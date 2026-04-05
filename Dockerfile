FROM python:3.14-alpine

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY main.py .
COPY users.json .

ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8080

EXPOSE 8080

CMD ["python", "-u", "main.py"]
