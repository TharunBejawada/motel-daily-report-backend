FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task
COPY . .
COPY token.json /app/token.json

RUN pip install --upgrade pip && pip install -r requirements.txt

CMD ["main.handler"]
