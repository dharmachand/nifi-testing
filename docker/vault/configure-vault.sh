#!/bin/sh
# Setup AppRole Auth and Transit service for IP Vault

export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN=00000000-0000-0000-0000-000000000000
export VAULT_SKIP_VERIFY=true

# Enable AppRole Auth
echo ' ' # blank line spacer
echo 'Enabling approle....'
vault auth enable approle
echo 'Enabling nifi transit....'
vault secrets enable -path=nifi transit
echo 'Enabling non-prod key....'
vault write -f nifi/keys/non-prod

# Create an ACL Policy for NIFI to encrypt/decrypts secret
echo ' ' # blank line spacer
echo 'Creating acl policy....'
vault policy write nifi-transit-policy nifi-transit-policy.hcl
echo 'Creating TOKEN FOR AUTH....'
vault token create -policy=nifi-transit-policy

# Create a named AppRole with Policy attached
echo ' ' # blank line spacer
echo 'Creating approle attached to policy....'
vault write auth/approle/role/nifi policies="nifi-transit-policy" token_ttl=0h token_max_ttl=0h

# Create a roleId for nifi
echo ' ' # blank line spacer
echo 'Creating approle role-id attached to policy....'
vault read -format=json auth/approle/role/nifi/role-id \
    | jq  -r '.data.role_id' > out/nifi_role_id

# Get a SecretID issued against the AppRole
echo ' ' # blank line spacer
echo 'Getting a secretId issued against approle....'
vault write -f -format=json auth/approle/role/nifi/secret-id \
	| jq -r '.data.secret_id' > out/nifi_secret_id

# Test approle
NIFI_ROLE_ID=`cat out/nifi_role_id`
NIFI_SECRET_ID=`cat out/nifi_secret_id`
vault write auth/approle/login role_id="$NIFI_ROLE_ID" \
  secret_id="$NIFI_SECRET_ID"

# Stop vault agent if running
echo ' ' # blank line spacer
echo 'Stopping vault agent if running....'
ps aux | grep -v "grep" | grep vault-agent | awk '{print $2}' | xargs kill

# Run vault agent
echo ' ' # blank line spacer
echo 'Running vault agent as background process....'
vault agent -config=vault-agent-config.hcl -log-level=debug > out/vault_agent.log 2>&1 &

vault_agent_pid=`ps aux | grep -v "grep" | grep vault-agent | awk '{print $2}'`
echo Vault Agent running with PID ${vault_agent_pid}.