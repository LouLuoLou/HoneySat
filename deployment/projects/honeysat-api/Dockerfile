# Start from Python 3.11 base image
FROM python:3.11

# Install pip packages
COPY ./requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# Copy the contents of the current directory into the image at /honeysat-api
COPY . /honeysat-api

# Set the working directory to /honeysat-api
WORKDIR /honeysat-api

# Set the PYTHONPATH environment variable
ENV PYTHONPATH=/honeysat-api

EXPOSE 8001
EXPOSE 8002
EXPOSE 5555

# Command to execute when the container starts
CMD ["python", "-u", "./TestsAndExamples/TestZMQInterface.py"]
