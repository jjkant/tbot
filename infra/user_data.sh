#!/bin/bash
set -e  # Exit on any error

# Enable logging
exec > >(tee /var/log/user_data.log|logger -t user_data) 2>&1

# Update packages and install Docker
apt-get update -y
apt-get install -y docker.io docker-compose git

# Start Docker service
systemctl start docker
systemctl enable docker

# Clone the repository
mkdir -p /home/ubuntu/patrolia
cd /home/ubuntu/patrolia

# Replace with your actual repository URL
git clone https://github.com/jjkant/tbot.git . || { echo "Git clone failed"; exit 1; }

# Navigate to the processing folder
cd processing

# Run Docker Compose
docker-compose up -d || { echo "Docker Compose failed"; exit 1; }

echo "Patrolia setup completed successfully!"
