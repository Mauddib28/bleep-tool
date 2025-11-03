# Use an official Ubuntu base image
FROM ubuntu:latest

# Set the working directory inside the container
WORKDIR /app

# Install git and any other dependencies required by your project
# Replace 'your_project_dependencies' with actual packages
RUN apt-get update && \
    apt-get install -y git cmake python3-pip python3.12-venv pkg-config libdbus-1-dev gir1.2-glib-2.0 libgirepository1.0-dev libcairo2-dev libgirepository-2.0-dev && \
    rm -rf /var/lib/apt/lists/*

# Clone your GitHub repository
# Replace 'your_username' and 'your_repository' with your details
RUN git clone https://github.com/Mauddib28/bleep-tool.git .

# Install project-specific dependencies (if any)
# For example, if it's a Python project:
RUN pip install -r requirements.txt --break-system-packages
RUN pip install -e . --break-system-packages

# Define the command to run when the container starts
# This will depend on how you want to test your project
# For example, to run a test script:
# CMD ["bash", "-c", "python your_test_script.py"]
# Or to simply keep the container running for manual interaction:
CMD ["bash"]
