# Use the official Python 3.12 image from the Docker Hub
FROM python:3.12

RUN apt-get update && apt-get install -y telnet

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt /app/requirements.txt

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY suchai_webinterface/ /app/suchai_webinterface/
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

WORKDIR /app/suchai_webinterface

# Expose the port the app runs on
EXPOSE 8000

# Define environment variable
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# # Run the Django app (assuming the app is run using manage.py and a development server)
# CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# CMD [ "python", "telnet_client_2.py" ]
# CMD ["tail", "-f", "/dev/null"]

CMD ["/app/start.sh"]
