
#!/bin/bash
# Update packages and install Docker
apt-get update -y
apt-get install -y docker.io docker-compose git

# Start Docker service
systemctl start docker
systemctl enable docker

# Clone the repository or set up the project
mkdir -p /home/ubuntu/twitch_bot
cd /home/ubuntu/twitch_bot

# Assuming files are hosted in a GitHub repository
git clone https://github.com/yourusername/yourrepository.git .

# Run Docker Compose
docker-compose up -d
