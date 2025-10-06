FROM public.ecr.aws/lambda/python:3.12

WORKDIR /var/task
COPY . .

RUN pip install --upgrade pip && pip install -r requirements.txt

CMD ["main.handler"]
