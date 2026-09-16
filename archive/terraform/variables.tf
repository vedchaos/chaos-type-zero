# ============================================================
# CHAOS TYPE ZERO — Terraform Variables
# ============================================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "chaos-type-zero"
}

variable "environment" {
  description = "Environment (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Public subnet CIDR"
  type        = string
  default     = "10.0.1.0/24"
}

variable "instance_type" {
  description = "EC2 instance type — t3.micro is free tier eligible (750 hrs/mo for 12 months)"
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size" {
  description = "Root EBS volume size (GB)"
  type        = number
  default     = 30
}

variable "data_volume_size" {
  description = "Data EBS volume size (GB)"
  type        = number
  default     = 20
}

variable "allowed_cidr_blocks" {
  description = "Allowed CIDR blocks for SSH access"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "github_repo" {
  description = "CTZ GitHub repo to clone"
  type        = string
  default     = "https://github.com/vedchaos/chaos-type-zero.git"
}

variable "tags" {
  description = "Common tags"
  type        = map(string)
  default = {
    Project   = "chaos-type-zero"
    ManagedBy = "terraform"
    Version   = "3.3"
  }
}
