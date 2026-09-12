output "service_account_email" {
  description = "Email of the backend service account (needed later to attach it to Cloud Run)."
  value       = google_service_account.backend.email
}

output "backend_key_path" {
  description = "Local path where the backend service-account JSON key was written."
  value       = local_file.backend_key_file.filename
}
