FROM public.ecr.aws/lambda/python:3.12

# Copy requirements and install dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy handler code
COPY src/handler.py ${LAMBDA_TASK_ROOT}/

# Set the CMD to the handler function
CMD [ "handler.handler" ]
