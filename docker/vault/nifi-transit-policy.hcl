# Permits token creation
path "auth/token/create" {
  capabilities = ["update"]
}
# Enable transit secrets engine
path "sys/mounts/transit" {
  capabilities = [ "create", "read", "update", "delete", "list" ]
}

# To read enabled secrets engines
path "sys/mounts" {
  capabilities = [ "read" ]
}

# Manage the transit secrets engine
path "transit/*" {
  capabilities = [ "create", "read", "update", "delete", "list" ]
}

# Manage the nifi secrets engine
path "nifi/*" {
  capabilities = [ "create", "read", "update", "delete", "list" ]
}
path "nifi/encrypt/non-prod" {
   capabilities = ["create", "read", "update", "delete", "list" ]
}

path "nifi/decrypt/non-prod" {
   capabilities = [ "create", "read", "update", "delete", "list" ]
}

# List existing keys in UI
path "nifi/keys" {
   capabilities = [ "list" ]
}

# Enable to select the orders key in UI
path "nifi/keys/non-prod" {
   capabilities = [ "read" ]
}