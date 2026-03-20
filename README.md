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
