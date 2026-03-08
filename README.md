# AI ORCHESTRATOR SERVICE

## SET UP ENV

### Create conda env
```bash
conda create -n ai-orchestrator-env python=3.13 uv -c conda-forge
```

### Activate conda env
```bash
conda activate ai-orchestrator-env
```

### Install dependancies
```bash
cd src
uv pip install -r reuirements.txt
```

## START APP
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 5000
```


## SETUP ALEMBIC

### Go to db folder
```bash
cd .\models\db
```
### Init alembic
```bash
alembic init -t async migrations
```

### Revesion code with alembic
```bash
alembic revision --autogenerate -m "commit message here"
```

### Aplly changes to DB
```bash
alembic upgrade head
```

--------------------------------------------------
--------------------------------------------------
--------------------------------------------------

# Deployment 

## Containerize Project

### Build Image
you should be in the root project
```bash
docker build -t ai-orchestrator:latest .
```
### Run app contaier locally and connect with Redis, PostgreSQL (they run on Docker-compose)
```bash
docker run -p 8000:8000 `
  --env-file src/.env `
  -e db_host=host.docker.internal `
  -e redis_host=host.docker.internal `
  -v "C:\Users\harth\AppData\Roaming\gcloud\application_default_credentials.json:/gcp/creds.json:ro" `
  -e GOOGLE_APPLICATION_CREDENTIALS=/gcp/creds.json `
  ai-orchestrator:latest
```

## Database Setup

### Step 1: Create Instance on Cloud SQL
This usually takes about 5 to 10 minutes

### Step 2: Create Your App's Database and Dedicated User for this database
Once the instance finishes spinning up, we need to create the specific database inside it.
- Make Database name match your .env file and create.
- Make User name match you .env file and also here put password for this user to use you DB

### Step 3: Install the Cloud SQL Auth Proxy (The Secure Bridge)
Cloud SQL Auth Proxy tool acts just like the SSH Tunnel we use for connecting with our remote DB.

1. Download the Auth Proxy for Windows directly from Google: Download [[cloud-sql-proxy-x64.exe](https://www.google.com/search?q=https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy-x64.exe)]

2. Rename the downloaded file to cloud-sql-proxy.exe and move it into the root folder of your project.

3. Find your Instance Connection Name: Go back to the GCP Console -> SQL -> Overview tab. Look for the "Connection name" (it will look like project-id:region:instance-name).

### Step 4: Run the Proxy Bridge
Open a new PowerShell terminal in your project root and run this command (replace with your exact connection name):
```bash
.\cloud-sql-proxy.exe your-project-id:your-region:your-instance-name --port 5432
```
Leave this terminal open! The encrypted bridge to Google Cloud is now active.

## Step 5: Update .env and Run Alembic
- Update Database configuration in your .env file
```bash
db_user=your-user-name
db_password=YourNewUserPasswordHere
db_name=DB-name
```
- Run your Alembic migrations
```bash
alembic upgrade head
```


## Installing Redis on a Linux VM

### 1. Update the Server and Install Redis
```bash
sudo apt update
sudo apt install redis-server -y
```

### 2. Configure Networking and Security
```bash
sudo nano /etc/redis/redis.conf
```
#### Step A (Networking): 
Search for 
```bash
bind 127.0.0.1 -::1
``` 
and change it to
```bash
bind 0.0.0.0
```

#### Step B (Security):
Scroll to the bottom of the file and add your password directive:
```bash
requirepass YourSuperSecretRedisPassword123
```
#### Save and exit (Ctrl+O, Enter, Ctrl+X).

### 3. Apply Changes and Enable Auto-Start
Restart the Redis service so it reads your new configuration file.
```bash
sudo systemctl restart redis-server
```

### Run this enable command next. 
It tells Linux, "If this VM ever reboots or crashes, automatically start Redis the moment the server turns back on."
```bash
sudo systemctl enable redis-server
```

### Connect with Remote Redis on VM locally
```bash
gcloud compute ssh redis-vm --zone=us-central1-c -- -L 6379:localhost:6379
```
instance name: redis-vm
region: us-central1-a
change them based on your VM
