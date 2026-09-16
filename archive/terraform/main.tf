# ============================================================
# CHAOS TYPE ZERO — Terraform Main (AWS EC2 Free Tier)
# ============================================================
# Deploy CTZ v3.3 on AWS EC2 t3.micro (FREE for 12 months)
# Includes: VPC, Security Group, EBS, S3, CloudWatch
# ============================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Local backend — no S3 bucket needed for first deploy
  backend "local" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

# ============================================================
# DATA SOURCES
# ============================================================
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Current AWS caller identity
data "aws_caller_identity" "current" {}

# ============================================================
# VPC
# ============================================================
resource "aws_vpc" "ctz_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_internet_gateway" "ctz_igw" {
  vpc_id = aws_vpc.ctz_vpc.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_subnet" "ctz_public" {
  vpc_id                  = aws_vpc.ctz_vpc.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public"
  }
}

resource "aws_route_table" "ctz_public" {
  vpc_id = aws_vpc.ctz_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ctz_igw.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

resource "aws_route_table_association" "ctz_public" {
  subnet_id      = aws_subnet.ctz_public.id
  route_table_id = aws_route_table.ctz_public.id
}

# ============================================================
# SECURITY GROUP
# ============================================================
resource "aws_security_group" "ctz_sg" {
  name        = "${var.project_name}-sg"
  description = "CTZ Security Group — SSH + all CTZ ports"
  vpc_id      = aws_vpc.ctz_vpc.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
    description = "SSH access"
  }

  # FastAPI Production Server
  ingress {
    from_port   = 9000
    to_port     = 9000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "CTZ FastAPI production server"
  }

  # Dashboard
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "CTZ Dashboard"
  }

  # Mobile API
  ingress {
    from_port   = 8081
    to_port     = 8081
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "CTZ Mobile API"
  }

  # Slack Bot
  ingress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Slack Bot"
  }

  # Grafana
  ingress {
    from_port   = 3001
    to_port     = 3001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Grafana dashboard"
  }

  # Prometheus
  ingress {
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Prometheus metrics"
  }

  # All outbound
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}

# ============================================================
# EC2 INSTANCE (Free Tier: t3.micro — 750 hrs/mo for 12 months)
# ============================================================
resource "aws_instance" "ctz_server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.ctz_key.key_name
  vpc_security_group_ids = [aws_security_group.ctz_sg.id]
  subnet_id              = aws_subnet.ctz_public.id

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    project_name = var.project_name
    github_repo  = var.github_repo
  })

  tags = {
    Name    = "${var.project_name}-server"
    Version = "3.3"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================================
# SSH KEY PAIR (auto-generated)
# ============================================================
resource "tls_private_key" "ctz_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "ctz_key" {
  key_name   = "${var.project_name}-key"
  public_key = tls_private_key.ctz_key.public_key_openssh
}

resource "local_file" "ctz_private_key" {
  content         = tls_private_key.ctz_key.private_key_pem
  filename        = "${path.module}/ctz-key.pem"
  file_permission = "0400"
}

# ============================================================
# EBS VOLUME (Data — 20GB free tier gp3)
# ============================================================
resource "aws_ebs_volume" "ctz_data" {
  availability_zone = "${var.aws_region}a"
  size              = var.data_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name = "${var.project_name}-data"
  }
}

resource "aws_volume_attachment" "ctz_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.ctz_data.id
  instance_id = aws_instance.ctz_server.id
}

# ============================================================
# S3 BUCKET (Backups — 5 GB free)
# ============================================================
resource "aws_s3_bucket" "ctz_backups" {
  bucket = "${var.project_name}-backups-${var.environment}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-backups"
  }
}

resource "aws_s3_bucket_versioning" "ctz_backups" {
  bucket = aws_s3_bucket.ctz_backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ctz_backups" {
  bucket = aws_s3_bucket.ctz_backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "ctz_backups" {
  bucket = aws_s3_bucket.ctz_backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# CLOUDWATCH ALARMS (Free: 10 alarms)
# ============================================================
resource "aws_cloudwatch_metric_alarm" "ctz_cpu" {
  alarm_name          = "${var.project_name}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "CTZ CPU utilization > 80%"

  dimensions = {
    InstanceId = aws_instance.ctz_server.id
  }
}

resource "aws_cloudwatch_metric_alarm" "ctz_status_check" {
  alarm_name          = "${var.project_name}-status-check-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "StatusCheckFailed"
  namespace           = "AWS/EC2"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "CTZ instance status check failed"

  dimensions = {
    InstanceId = aws_instance.ctz_server.id
  }
}

# ============================================================
# OUTPUTS
# ============================================================
output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.ctz_server.id
}

output "instance_public_ip" {
  description = "CTZ server public IP"
  value       = aws_instance.ctz_server.public_ip
}

output "instance_public_dns" {
  description = "CTZ server public DNS"
  value       = aws_instance.ctz_server.public_dns
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh -i ctz-key.pem ubuntu@${aws_instance.ctz_server.public_ip}"
}

output "server_url" {
  description = "CTZ FastAPI production server"
  value       = "http://${aws_instance.ctz_server.public_ip}:9000"
}

output "server_swagger" {
  description = "CTZ Swagger docs"
  value       = "http://${aws_instance.ctz_server.public_ip}:9000/docs"
}

output "dashboard_url" {
  description = "CTZ Dashboard"
  value       = "http://${aws_instance.ctz_server.public_ip}:8080"
}

output "api_url" {
  description = "CTZ Mobile API"
  value       = "http://${aws_instance.ctz_server.public_ip}:8081"
}

output "prometheus_url" {
  description = "Prometheus metrics"
  value       = "http://${aws_instance.ctz_server.public_ip}:9090"
}

output "grafana_url" {
  description = "Grafana dashboard"
  value       = "http://${aws_instance.ctz_server.public_ip}:3001"
}

output "s3_bucket_name" {
  description = "Backup S3 bucket"
  value       = aws_s3_bucket.ctz_backups.id
}

output "private_key_saved_to" {
  description = "SSH private key saved to"
  value       = local_file.ctz_private_key.filename
}
