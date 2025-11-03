#!/bin/bash

# Build the Docker VM Image
echo -e "[*] Building Docker VM Images"
docker build -t bleep-project-image .

# Start Bash in Bleep Container while passing D-Bus ability
echo -e "[*] Jumping into the BLEEP Container"
docker run -v /var/run/dbus/:/var/run/dbus/:z --privileged -it bleep-project-image bash
