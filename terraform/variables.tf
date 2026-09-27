variable "project_id" {
  description = "GCP project ID to deploy into."
  type        = string
}

variable "region" {
  description = "Default GCP region (used for Vertex AI)."
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Name of the GCS bucket holding the professional-history markdown."
  type        = string
}

variable "bucket_location" {
  description = "GCS bucket location (distinct from the Vertex AI region)."
  type        = string
  default     = "US"
}

variable "service_account_id" {
  description = "Account ID (local part of the email) for the backend service account."
  type        = string
  default     = "digital-twin-backend"
}

variable "service_account_display_name" {
  description = "Display name for the backend service account."
  type        = string
  default     = "Digital Twin Backend"
}

variable "credentials_file" {
  description = "Optional path to a GCP service-account JSON key for Terraform's own auth. Leave empty to use Application Default Credentials."
  type        = string
  default     = ""
}

variable "backend_key_output_path" {
  description = "Local path to write the generated backend service-account JSON key."
  type        = string
  default     = "./backend-sa-key.json"
}

variable "artifact_repository_id" {
  description = "Artifact Registry repository ID holding the built frontend/backend images."
  type        = string
  default     = "digital-twin"
}

variable "cloud_run_service_name" {
  description = "Name of the Cloud Run service running nginx + backend + redis."
  type        = string
  default     = "digital-twin"
}

variable "history_object_path" {
  description = "Object path (within bucket_name) of the professional-history markdown."
  type        = string
  default     = "professional-history.md"
}

variable "chat_log_prefix" {
  description = "Object prefix (within bucket_name) where chat exchanges are logged."
  type        = string
  default     = "chat-logs/"
}

variable "chat_log_retention_days" {
  description = "Days after which chat-log objects are deleted by a bucket lifecycle rule."
  type        = number
  default     = 90
}

variable "max_instances" {
  description = "Maximum Cloud Run instances (cost guardrail against traffic bursts)."
  type        = number
  default     = 2
}

variable "image_tag" {
  description = "Image tag for the frontend/backend containers when the Cloud Run service is first created. After that, the deploy-on-master Cloud Build trigger rolls out images (tagged with the commit SHA) and Terraform ignores image changes."
  type        = string
  default     = "latest"
}

variable "github_owner" {
  description = "GitHub owner of the repository the deploy trigger watches."
  type        = string
  default     = "pimorandi"
}

variable "github_repo" {
  description = "GitHub repository name the deploy trigger watches."
  type        = string
  default     = "digital-twin"
}

variable "turnstile_site_key" {
  description = "Public Cloudflare Turnstile site key, baked into the frontend bundle by the deploy trigger."
  type        = string
}
