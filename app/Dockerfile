FROM python:3.8-slim

WORKDIR /app
## Since i am already inside the app directory, no need to copy again the app folder
#

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# COPY app/ .
COPY . .

EXPOSE 5000

ENTRYPOINT [ "app" ]

CMD ["python", "app.py"]