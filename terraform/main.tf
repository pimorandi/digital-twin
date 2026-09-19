provider "google" {
  project     = var.project_id
  region      = var.region
  credentials = var.credentials_file != "" ? file(var.credentials_file) : null
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "aiplatform" {
  project = var.project_id
  service = "aiplatform.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "run" {
  project = var.project_id
  service = "run.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "secretmanager" {
  project = var.project_id
  service = "secretmanager.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry" {
  project = var.project_id
  service = "artifactregistry.googleapis.com"

  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  project = var.project_id
  service = "cloudbuild.googleapis.com"

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

  lifecycle_rule {
    condition {
      age            = var.chat_log_retention_days
      matches_prefix = [var.chat_log_prefix]
    }
    action {
      type = "Delete"
    }
  }
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

# Create-only (no read/overwrite/delete) and limited to the chat-log prefix, so
# the backend can log conversations but can't touch the professional history.
resource "google_storage_bucket_iam_member" "chat_log_writer" {
  bucket = google_storage_bucket.history.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.backend.email}"

  condition {
    title      = "chat-logs-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${var.bucket_name}/objects/${var.chat_log_prefix}\")"
  }
}

# Bot-protection secrets. Only the empty secret "shells" live in Terraform: the
# values are added out-of-band (gcloud secrets versions add ...) so they never
# end up in the Terraform state. See docs/architecture.md, "Bot protection".
resource "google_secret_manager_secret" "turnstile_secret_key" {
  project   = var.project_id
  secret_id = "turnstile-secret-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "session_signing_key" {
  project   = var.project_id
  secret_id = "session-signing-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_iam_member" "turnstile_secret_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.turnstile_secret_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_secret_manager_secret_iam_member" "session_signing_key_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.session_signing_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
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

# Cloud Run's own infrastructure (the Cloud Run service agent) needs explicit
# permission to *act as* digital-twin-sa before it can attach it to a revision
# and mint tokens for it — attaching a service account isn't enough on its
# own. Discovered live: without this, the metadata server refuses to issue a
# token for digital-twin-sa with a 403, and every GCS/Vertex AI call fails.
resource "google_service_account_iam_member" "run_agent_can_act_as_backend" {
  service_account_id = google_service_account.backend.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.current.number}@serverless-robot-prod.iam.gserviceaccount.com"

  depends_on = [google_project_service.run]
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  format        = "DOCKER"

  depends_on = [google_project_service.artifact_registry]
}

# Explicit rather than assumed: newer projects don't reliably grant Cloud
# Build's own service agent registry-write access by default.
resource "google_project_iam_member" "cloudbuild_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.current.number}@cloudbuild.gserviceaccount.com"

  depends_on = [google_project_service.cloudbuild]
}

resource "google_cloud_run_v2_service" "app" {
  project  = var.project_id
  name     = var.cloud_run_service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  # This is a low-traffic demo service expected to be iterated on/redeployed
  # freely — not a production service that needs protection from accidental
  # `terraform destroy`.
  deletion_protection = false

  template {
    service_account = google_service_account.backend.email

    # Cost guardrail: caps how far a burst of traffic can scale (and spend).
    scaling {
      max_instance_count = var.max_instances
    }

    containers {
      name  = "nginx"
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/frontend:latest"

      ports {
        container_port = 80
      }

      env {
        name  = "BACKEND_UPSTREAM"
        value = "127.0.0.1"
      }

      depends_on = ["backend"]
    }

    containers {
      name  = "backend"
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/backend:latest"

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.region
      }
      env {
        name  = "HISTORY_GCS_URI"
        value = "gs://${var.bucket_name}/${var.history_object_path}"
      }
      env {
        name  = "CHAT_LOG_GCS_URI"
        value = "gs://${var.bucket_name}/${var.chat_log_prefix}"
      }
      env {
        name = "TURNSTILE_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.turnstile_secret_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SESSION_SIGNING_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.session_signing_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "REDIS_URL"
        value = "redis://localhost:6379/0"
      }

      startup_probe {
        tcp_socket {
          port = 8000
        }
      }

      depends_on = ["redis"]
    }

    containers {
      name  = "redis"
      image = "redis:7-alpine"

      startup_probe {
        tcp_socket {
          port = 6379
        }
      }
    }
  }

  depends_on = [
    google_project_service.run,
    google_storage_bucket_iam_member.history_bucket_reader,
    google_storage_bucket_iam_member.chat_log_writer,
    google_secret_manager_secret_iam_member.turnstile_secret_key_accessor,
    google_secret_manager_secret_iam_member.session_signing_key_accessor,
    google_project_iam_member.vertex_ai_user,
    google_service_account_iam_member.run_agent_can_act_as_backend,
  ]
}

# Intentionally not granted while the service is still in testing: without
# this binding (or an equivalent), Cloud Run requires an authenticated,
# authorized caller for every request — the service is unreachable by the
# public internet. Re-add a `google_cloud_run_v2_service_iam_member` granting
# `roles/run.invoker` to `allUsers` here once ready to go public again (see
# docs/architecture.md — nginx is meant to be the public entry point
# eventually, just not yet).
