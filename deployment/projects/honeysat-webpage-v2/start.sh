#!/bin/bash

# Run the telnet client in the background
python telnet_client_2.py &

# Start the Django development server
python manage.py runserver 0.0.0.0:8000