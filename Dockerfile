# Use official Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app's code
COPY . .

# Run the FastAPI server on Cloud Run's required port (8080)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
