# Honeysat Web Interface
This service is used in Honeysat CSP stack.

## Configuration
The service can be configured through a bunch of environment variables.
The purpose of each variable should be obvious.
Here is a short description of the most important variables:

```bash
# Mission details
MISSION_NAME=YOUR_MISSION_NAME
ENTITY_NAME=YOUR_ENTITY_NAME
FAKE_WEB_GIT_REPO_URL=https://github.com/your-user/your-repo

# Ground station coordinates
GROUND_STATION_LAT=YOUR_LATITUDE
GROUND_STATION_LON=YOUR_LONGITUDE

# Satellite information
SATELLITE_NAME_TLE=YOUR_SATELLITE_NAME
MISSION_REAL_MANUAL_URL=https://www.your-organization.com/manuals/your-mission

# Logo information
MISSION_LOGO_URL=https://your-logo-url.com/logo.svg
LOGO_STYLE=filter: invert(1);  # Customize style if needed

# Developer information
DEVELOPER_NAME_1=YourFirstDeveloperName
DEVELOPER_NAME_2=YourSecondDeveloperName

# Documentation URL
# You can use pastebin.com, set to unlisted and paste here the RAW url
FAKE_DOCS_V2_URL=https://your-docs-url.com/docs
```

These variables handle django framework's settings:
```yaml
      DJANGO_DEBUG: "False"
      SECRET_KEY: "django-insecure-yg^om13za-@h6=ylvtlvb7u-iik5ecruxj%de=h)a1_@7stkuv"
```

These variables provide the ground station's connection info:
```yaml
      TELNET_HOST: "suchai-gs"
      TELNET_PORT: "1234"
```

These variables are used for logging purposes:
```yaml
      MONGO_DB_NAME: "********"
      MONGO_USER_NAME: "********"
      MONGO_PASSWORD: "********"
      MONGO_IP: "logs_mongodb"
      MONGO_PORT: "27017"
```
