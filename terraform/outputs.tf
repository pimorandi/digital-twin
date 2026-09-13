output "service_account_email" {
  description = "Email of the backend service account, attached to the Cloud Run service."
  value       = google_service_account.backend.email
}

output "cloud_run_url" {
  description = "Public URL of the deployed Cloud Run service."
  value       = google_cloud_run_v2_service.app.uri
}

output "backend_key_path" {
  description = "Local path where the backend service-account JSON key was written."
  value       = local_file.backend_key_file.filename
}
