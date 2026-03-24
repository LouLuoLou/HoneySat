# SUCHAI Ground Station
This is an actual ground station software implementation used in a CubeSat mission.

## Configuration
The following environment variables are used at run-time for the purpose of logging to a MongoDB:

```yaml
      MONGO_DB_NAME: "********"
      MONGO_USER_NAME: "********"
      MONGO_PASSWORD: "********"
      MONGO_IP: "logs_mongodb"
      MONGO_PORT: "27017"
```

Also, the following docker build arguments are used when building the docker image:

```yaml
        CONSOLE_PROMPT: "STARLINK"
        BANNER_CONSOLE_NAME: "STARLINK"
```
