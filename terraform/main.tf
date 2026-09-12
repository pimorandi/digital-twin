provider "google" {
  project     = var.project_id
  region      = var.region
  credentials = var.credentials_file != "" ? file(var.credentials_file) : null
}

resource "google_project_service" "aiplatform" {
  project = var.project_id
  service = "aiplatform.googleapis.com"

  disable_on_destroy = false
}

resource "google_storage_bucket" "history" {
  name          = var.bucket_name
  project       = var.project_id
  location      = var.bucket_location
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
}

resource "google_service_account" "backend" {
  project      = var.project_id
  account_id   = var.service_account_id
  display_name = var.service_account_display_name
}

resource "google_storage_bucket_iam_member" "history_bucket_reader" {
  bucket = google_storage_bucket.history.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"

  depends_on = [google_project_service.aiplatform]
}

resource "google_service_account_key" "backend_key" {
  service_account_id = google_service_account.backend.name
}

resource "local_file" "backend_key_file" {
  content         = base64decode(google_service_account_key.backend_key.private_key)
  filename        = var.backend_key_output_path
  file_permission = "0600"
}
