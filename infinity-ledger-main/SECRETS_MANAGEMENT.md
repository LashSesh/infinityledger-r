# Secrets Management Guide - Infinity Ledger

## Overview

This guide provides comprehensive instructions for managing sensitive credentials and secrets across different deployment environments.

## Table of Contents

1. [Security Principles](#security-principles)
2. [Development Environment](#development-environment)
3. [CI/CD Environment](#cicd-environment)
4. [Staging Environment](#staging-environment)
5. [Production Environment](#production-environment)
6. [Secret Rotation](#secret-rotation)
7. [Auditing and Compliance](#auditing-and-compliance)

---

## Security Principles

### Never Commit Secrets

- **Never** commit secrets to version control
- Use `.gitignore` to exclude `.env` files (except templates)
- Review git history before pushing to ensure no secrets leaked
- Use pre-commit hooks to scan for secrets (e.g., `git-secrets`, `detect-secrets`)

### Principle of Least Privilege

- Grant minimum required permissions
- Use separate credentials for each environment
- Rotate credentials regularly
- Revoke access immediately when no longer needed

### Defense in Depth

- Use multiple layers of security
- Encrypt secrets at rest and in transit
- Use network segmentation
- Enable audit logging

---

## Development Environment

### Method 1: Local .env File (Recommended for Development)

```bash
# 1. Copy template
cp .env.example .env

# 2. Edit with your development credentials
vim .env

# 3. Set required variables
AUTH_TOKEN_REQUIRED=false
MEF_API_TOKEN=dev-token-placeholder
QUALITY_TOKEN=dev-token-placeholder

# 4. Start services
docker compose -f docker-compose.ci.yml --profile compare up -d
```

**Security Notes**:
- `.env` is gitignored by default
- Use weak credentials for local development
- Never use production credentials locally

### Method 2: Environment Variables

```bash
# Export variables in your shell
export AUTH_TOKEN_REQUIRED=false
export MEF_API_TOKEN=dev-token
export QUALITY_TOKEN=dev-token

# Start services
docker compose -f docker-compose.ci.yml --profile compare up -d
```

### Method 3: direnv (Automatic Environment Loading)

```bash
# 1. Install direnv
brew install direnv  # macOS
# or
sudo apt install direnv  # Linux

# 2. Create .envrc file
cat > .envrc << 'EOF'
export AUTH_TOKEN_REQUIRED=false
export MEF_API_TOKEN=dev-token
export QUALITY_TOKEN=dev-token
EOF

# 3. Allow direnv
direnv allow

# 4. Secrets automatically loaded when entering directory
cd /path/to/infinity-ledger
```

---

## CI/CD Environment

### GitHub Actions Secrets

#### Setting Up Secrets

1. Navigate to repository settings
2. Go to "Secrets and variables" → "Actions"
3. Click "New repository secret"
4. Add secrets:
   - `MEF_API_TOKEN`: API authentication token
   - `QUALITY_TOKEN`: Quality service token
   - `GRAFANA_ADMIN_PASSWORD`: Grafana admin password (if using monitoring)

#### Using Secrets in Workflows

```yaml
jobs:
  build-test:
    runs-on: ubuntu-24.04
    env:
      # Public configuration
      AUTH_TOKEN_REQUIRED: "true"
      
      # Secrets from GitHub
      MEF_API_TOKEN: ${{ secrets.MEF_API_TOKEN }}
      QUALITY_TOKEN: ${{ secrets.QUALITY_TOKEN }}
```

#### Best Practices

- Use separate secrets for each environment (dev, staging, prod)
- Prefix secrets with environment: `PROD_MEF_API_TOKEN`, `STAGING_MEF_API_TOKEN`
- Use GitHub Environments for additional access control
- Enable branch protection to limit secret access

### GitHub Environments

Create separate environments for better control:

```yaml
jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval
    env:
      MEF_API_TOKEN: ${{ secrets.PROD_MEF_API_TOKEN }}
```

**Benefits**:
- Required reviewers for production deployments
- Environment-specific secrets
- Deployment protection rules

---

## Staging Environment

### Method 1: Docker Secrets (File-based)

```bash
# 1. Create secret files (on staging server)
mkdir -p /run/secrets
echo "staging-api-token-xyz" > /run/secrets/mef_api_token
echo "staging-quality-token-xyz" > /run/secrets/quality_token
chmod 600 /run/secrets/*

# 2. Update docker-compose to use secrets
# Add to docker-compose.staging.yml:
services:
  api:
    secrets:
      - mef_api_token
      - quality_token
    environment:
      - AUTH_TOKEN_REQUIRED=true

secrets:
  mef_api_token:
    file: /run/secrets/mef_api_token
  quality_token:
    file: /run/secrets/quality_token

# 3. Start services
docker compose -f docker-compose.staging.yml up -d
```

### Method 2: AWS Secrets Manager

```bash
# 1. Store secrets in AWS
aws secretsmanager create-secret \
  --name infinity-ledger/staging/mef-api-token \
  --secret-string "staging-api-token-xyz"

aws secretsmanager create-secret \
  --name infinity-ledger/staging/quality-token \
  --secret-string "staging-quality-token-xyz"

# 2. Create script to fetch secrets
cat > fetch-secrets.sh << 'EOF'
#!/bin/bash
export MEF_API_TOKEN=$(aws secretsmanager get-secret-value \
  --secret-id infinity-ledger/staging/mef-api-token \
  --query SecretString --output text)

export QUALITY_TOKEN=$(aws secretsmanager get-secret-value \
  --secret-id infinity-ledger/staging/quality-token \
  --query SecretString --output text)
EOF

# 3. Source and start services
source fetch-secrets.sh
docker compose -f docker-compose.staging.yml up -d
```

**IAM Policy Required**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:infinity-ledger/staging/*"
    }
  ]
}
```

---

## Production Environment

### Method 1: Docker Swarm Secrets (Recommended for Docker Swarm)

```bash
# 1. Initialize Docker Swarm (if not already)
docker swarm init

# 2. Create secrets
echo "production-api-token-xyz" | docker secret create mef_api_token -
echo "production-quality-token-xyz" | docker secret create quality_token -

# 3. List secrets (values are encrypted)
docker secret ls

# 4. Deploy stack with secrets
docker stack deploy -c docker-compose.production.yml infinity-ledger

# 5. Verify secrets are mounted
docker exec $(docker ps -q -f name=infinity-ledger_api) \
  ls -la /run/secrets/
```

**docker-compose.production.yml**:
```yaml
services:
  api:
    secrets:
      - mef_api_token
      - quality_token
    environment:
      - AUTH_TOKEN_REQUIRED=true
      # Read from secret files
      - MEF_API_TOKEN_FILE=/run/secrets/mef_api_token
      - QUALITY_TOKEN_FILE=/run/secrets/quality_token

secrets:
  mef_api_token:
    external: true
  quality_token:
    external: true
```

### Method 2: HashiCorp Vault (Recommended for Kubernetes/Complex Deployments)

#### Setup Vault

```bash
# 1. Start Vault server
docker run -d \
  --name vault \
  --cap-add=IPC_LOCK \
  -e 'VAULT_DEV_ROOT_TOKEN_ID=myroot' \
  -p 8200:8200 \
  vault:1.13.0

# 2. Initialize Vault client
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='myroot'

# 3. Enable KV secrets engine
vault secrets enable -path=infinity-ledger kv-v2

# 4. Store secrets
vault kv put infinity-ledger/production/api \
  mef_api_token="production-api-token-xyz" \
  quality_token="production-quality-token-xyz"

# 5. Create policy for read access
cat > infinity-ledger-policy.hcl << EOF
path "infinity-ledger/data/production/*" {
  capabilities = ["read"]
}
EOF

vault policy write infinity-ledger infinity-ledger-policy.hcl

# 6. Create token for application
vault token create -policy=infinity-ledger
```

#### Integrate with Application

**Option A: Vault Agent Sidecar**
```yaml
services:
  vault-agent:
    image: vault:1.13.0
    command: agent -config=/vault/config/agent.hcl
    volumes:
      - ./vault-config:/vault/config
      - vault-secrets:/vault/secrets
    environment:
      - VAULT_ADDR=http://vault:8200

  api:
    depends_on:
      - vault-agent
    volumes:
      - vault-secrets:/run/secrets:ro
    environment:
      - AUTH_TOKEN_REQUIRED=true
      - MEF_API_TOKEN_FILE=/run/secrets/mef_api_token
      - QUALITY_TOKEN_FILE=/run/secrets/quality_token
```

**Option B: Application-side Vault Client**
```python
import hvac

# Connect to Vault
client = hvac.Client(url='http://vault:8200', token=os.environ['VAULT_TOKEN'])

# Read secrets
secret = client.secrets.kv.v2.read_secret_version(
    path='production/api',
    mount_point='infinity-ledger'
)

mef_api_token = secret['data']['data']['mef_api_token']
quality_token = secret['data']['data']['quality_token']
```

### Method 3: Cloud-Native Secret Management

#### AWS ECS with Secrets Manager

```json
{
  "containerDefinitions": [
    {
      "name": "api",
      "image": "infinity-ledger/api:latest",
      "secrets": [
        {
          "name": "MEF_API_TOKEN",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:infinity-ledger/prod/mef-api-token"
        },
        {
          "name": "QUALITY_TOKEN",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:infinity-ledger/prod/quality-token"
        }
      ]
    }
  ]
}
```

#### Kubernetes Secrets

```yaml
# Create secret
apiVersion: v1
kind: Secret
metadata:
  name: infinity-ledger-secrets
type: Opaque
data:
  mef_api_token: <base64-encoded-token>
  quality_token: <base64-encoded-token>

---
# Use in deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  template:
    spec:
      containers:
      - name: api
        env:
        - name: MEF_API_TOKEN
          valueFrom:
            secretKeyRef:
              name: infinity-ledger-secrets
              key: mef_api_token
        - name: QUALITY_TOKEN
          valueFrom:
            secretKeyRef:
              name: infinity-ledger-secrets
              key: quality_token
```

---

## Secret Rotation

### Rotation Schedule

- **Development**: As needed (low priority)
- **Staging**: Every 90 days
- **Production**: Every 30-90 days (depending on sensitivity)
- **Compromised Secrets**: Immediately

### Rotation Procedure

#### 1. Generate New Secrets

```bash
# Generate strong random tokens
NEW_API_TOKEN=$(openssl rand -base64 32)
NEW_QUALITY_TOKEN=$(openssl rand -base64 32)
```

#### 2. Update Secret Store

**Docker Swarm**:
```bash
# Update secrets (requires recreating service)
echo "$NEW_API_TOKEN" | docker secret create mef_api_token_v2 -
docker service update --secret-rm mef_api_token \
  --secret-add source=mef_api_token_v2,target=mef_api_token \
  infinity-ledger_api
```

**Vault**:
```bash
# Update in Vault
vault kv put infinity-ledger/production/api \
  mef_api_token="$NEW_API_TOKEN" \
  quality_token="$NEW_QUALITY_TOKEN"

# Restart services to pick up new secrets
docker compose -f docker-compose.production.yml restart api
```

#### 3. Verify New Secrets

```bash
# Test with new credentials
curl -H "Authorization: Bearer $NEW_API_TOKEN" \
  http://localhost:8080/healthz
```

#### 4. Revoke Old Secrets

```bash
# Remove old secrets from Vault
vault kv delete infinity-ledger/production/api-old

# Remove from Docker
docker secret rm mef_api_token_old
```

### Automated Rotation

**Example: Rotate secrets every 90 days**

```bash
#!/bin/bash
# rotate-secrets.sh

# Check secret age
SECRET_AGE=$(vault kv metadata get -format=json infinity-ledger/production/api | \
  jq -r '.data.created_time')

AGE_DAYS=$(( ($(date +%s) - $(date -d "$SECRET_AGE" +%s)) / 86400 ))

if [ $AGE_DAYS -gt 90 ]; then
  echo "Rotating secrets (age: $AGE_DAYS days)"
  
  # Generate new secrets
  NEW_API_TOKEN=$(openssl rand -base64 32)
  NEW_QUALITY_TOKEN=$(openssl rand -base64 32)
  
  # Store in Vault
  vault kv put infinity-ledger/production/api \
    mef_api_token="$NEW_API_TOKEN" \
    quality_token="$NEW_QUALITY_TOKEN"
  
  # Trigger service restart
  docker compose -f docker-compose.production.yml restart api
  
  echo "Secrets rotated successfully"
else
  echo "Secrets are current (age: $AGE_DAYS days)"
fi
```

**Cron Job**:
```bash
# Add to crontab (run weekly)
0 2 * * 1 /opt/infinity-ledger/rotate-secrets.sh
```

---

## Auditing and Compliance

### Enable Audit Logging

#### Vault Audit Logging

```bash
# Enable file audit device
vault audit enable file file_path=/vault/logs/audit.log

# View audit logs
tail -f /vault/logs/audit.log | jq .
```

#### Docker Secret Access Logging

```bash
# Enable Docker audit logging
cat > /etc/docker/daemon.json << EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3",
    "labels": "audit=true"
  }
}
EOF

systemctl restart docker
```

### Compliance Checklist

- [ ] All secrets stored in secure secret management system
- [ ] No secrets in version control (scan with `git-secrets`)
- [ ] Secrets encrypted at rest
- [ ] Secrets encrypted in transit (TLS)
- [ ] Access to secrets logged and audited
- [ ] Secrets rotated according to schedule
- [ ] Least privilege access implemented
- [ ] Separate credentials per environment
- [ ] Incident response plan for secret compromise
- [ ] Regular security audits conducted

### Secret Scanning

#### Install git-secrets

```bash
# Install
brew install git-secrets  # macOS
# or
git clone https://github.com/awslabs/git-secrets.git
cd git-secrets && make install

# Configure for repository
cd /path/to/infinity-ledger
git secrets --install
git secrets --register-aws
git secrets --add 'token|password|secret|key'
```

#### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Scan for secrets
git secrets --pre_commit_hook -- "$@"
```

### Monitoring and Alerting

Set up alerts for:
- Unauthorized secret access attempts
- Secret rotation overdue
- Failed authentication attempts
- Unusual access patterns

**Example Prometheus Alert**:
```yaml
groups:
  - name: secrets
    rules:
      - alert: SecretRotationOverdue
        expr: (time() - secret_last_rotated_timestamp) > (90 * 24 * 3600)
        annotations:
          summary: "Secret rotation overdue for {{ $labels.secret_name }}"
```

---

## Quick Reference

### Development
```bash
cp .env.example .env
# Edit .env with dev credentials
docker compose -f docker-compose.ci.yml --profile compare up -d
```

### CI/CD (GitHub Actions)
- Set secrets in repository settings
- Use `${{ secrets.SECRET_NAME }}` in workflows

### Staging (Docker Secrets)
```bash
echo "token" | docker secret create mef_api_token -
docker compose -f docker-compose.staging.yml up -d
```

### Production (Vault)
```bash
vault kv put infinity-ledger/production/api mef_api_token="token"
# Use Vault agent or application integration
```

---

## Additional Resources

- [Docker Secrets Documentation](https://docs.docker.com/engine/swarm/secrets/)
- [HashiCorp Vault Documentation](https://www.vaultproject.io/docs)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)

---

**Last Updated**: 2025-10-13
**Version**: 1.0.0
