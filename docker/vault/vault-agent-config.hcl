exit_after_auth = false
pid_file = "./pidfile"

auto_auth {
   method "approle" {
       mount_path = "auth/approle"
       config = {
           role_id_file_path = "nifi_role_id"
           secret_id_file_path = "nifi_secret_id"
           remove_secret_id_file_after_reading = false
       }
   }

   sink "file" {
       config = {
           path = "approleToken"
       }
   }
}

cache {
   use_auto_auth_token = true
}

listener "tcp" {
   address = "0.0.0.0:8007"
   tls_disable = true
   require_request_header = true
}

vault {
   address = "http://127.0.0.1:8200"
}