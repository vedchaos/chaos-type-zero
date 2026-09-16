# ============================================================
# CHAOS TYPE ZERO — Terraform Outputs
# ============================================================

output "dashboard_url" {
  description = "CTZ Dashboard URL"
  value       = "http://${aws_instance.ctz_server.public_ip}:8080"
}

output "api_url" {
  description = "CTZ API URL"
  value       = "http://${aws_instance.ctz_server.public_ip}:8081"
}

output "prometheus_url" {
  description = "Prometheus URL"
  value       = "http://${aws_instance.ctz_server.public_ip}:9090"
}

output "grafana_url" {
  description = "Grafana URL"
  value       = "http://${aws_instance.ctz_server.public_ip}:3001"
}

output "ssh_command" {
  description = "SSH command to connect"
  value       = "ssh -i ${var.key_pair_name}.pem ubuntu@${aws_instance.ctz_server.public_ip}"
}

output "instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.ctz_server.id
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.ctz_vpc.id
}

output "security_group_id" {
  description = "Security Group ID"
  value       = aws_security_group.ctz_sg.id
}
