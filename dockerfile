# Use an official Ubuntu base image
FROM ubuntu:latest

# Set the working directory inside the container
WORKDIR /app

# System dependencies.
#  - python3-gi / python3-gi-cairo: provide PyGObject via apt so setup.py's
#    system-detection path is used and PyGObject is NOT rebuilt from source.
#  - libdbus-1-dev + pkg-config: needed to build dbus-python from pip.
#  - libgirepository*-dev / libcairo2-dev: retained for the pip PyGObject
#    build fallback if the system binding is ever unavailable.
#  - python3-venv (unpinned): avoids breakage when the ubuntu:latest default
#    Python advances past 3.12.
RUN apt-get update && \
    apt-get install -y git cmake python3-pip python3-venv pkg-config \
        python3-gi python3-gi-cairo \
        libdbus-1-dev gir1.2-glib-2.0 libgirepository1.0-dev libgirepository-2.0-dev libcairo2-dev && \
    rm -rf /var/lib/apt/lists/*

# Clone your GitHub repository
# Replace 'your_username' and 'your_repository' with your details
RUN git clone https://github.com/Mauddib28/bleep-tool.git .

# Install BLEEP and its runtime dependencies. setup.py is the single source of
# truth: it pulls dbus-python and PyYAML, and skips PyGObject because the system
# binding (python3-gi) is already present. The separate `requirements.txt` step
# was removed — it re-listed PyGObject and would force a redundant source build.
RUN pip install -e . --break-system-packages

# Define the command to run when the container starts
# This will depend on how you want to test your project
# For example, to run a test script:
# CMD ["bash", "-c", "python your_test_script.py"]
# Or to simply keep the container running for manual interaction:
CMD ["bash"]
