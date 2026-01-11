# Use lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose port
EXPOSE 5000

# Run app with Gunicorn (production-ready)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--reload"]
