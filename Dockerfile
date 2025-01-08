# Use an official Python runtime as the base image
FROM python:3.9-slim

# Set environment variables to prevent bytecode files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev gcc --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p qr_codes 


# Expose the port the app runs on
EXPOSE 5000

# Command to create/update the database and start the app
CMD ["python","app.py"]
