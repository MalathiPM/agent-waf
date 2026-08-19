output "alb_dns_name" {
  description = "Public hostname of the WAF."
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "Push the container image here."
  value       = aws_ecr_repository.waf.repository_url
}

output "log_group" {
  description = "CloudWatch log group for the service."
  value       = aws_cloudwatch_log_group.waf.name
}
