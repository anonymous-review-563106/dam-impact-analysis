# 1️⃣ Use Python 3.9 as the base image
FROM python:3.9

# 2️⃣ Set up the working directory inside the container
WORKDIR /app

# 3️⃣ Copy project files into the container
COPY . /app

# 4️⃣ Install system dependencies (GDAL, gcloud, and other required libraries)
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    curl \
    apt-transport-https \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# 5️⃣ Install Google Cloud SDK (gcloud) using the official installer
RUN curl -O https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-sdk-441.0.0-linux-x86_64.tar.gz \
    && tar -xvzf google-cloud-sdk-441.0.0-linux-x86_64.tar.gz \
    && rm google-cloud-sdk-441.0.0-linux-x86_64.tar.gz \
    && mv google-cloud-sdk /usr/local/gcloud \
    && /usr/local/gcloud/install.sh --quiet

# 6️⃣ Ensure gcloud is in the system PATH
ENV PATH="/usr/local/gcloud/bin:${PATH}"

# 7️⃣ Set up Google Cloud authentication (Service Account JSON)
ENV GOOGLE_APPLICATION_CREDENTIALS="/app/service-account.json"

# 8️⃣ Copy the service account JSON into the container
COPY service-account.json /app/

# 9️⃣ Install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 🔟 Expose the Streamlit port
EXPOSE 8501

# 1️⃣1️⃣ Run the Streamlit application
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
