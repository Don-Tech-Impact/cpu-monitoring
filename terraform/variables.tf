##############################################
# Terraform Variables
##############################################

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "subnet_prefix" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "ami_name_filter" {
  description = "AMI name filter for Ubuntu"
  type = object({
    description = string
    name        = string
    default     = string
    type        = string
  })
  default = {
    description = "Filter for Ubuntu AMI"
    name        = "name"
    default     = "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"
    type        = "string"
  }
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"
}

variable "db_username" {
  description = "RDS master username"
  type        = string
  default     = "finance_user"
  sensitive   = true
}

variable "db_password" {
  description = "RDS master password"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "RDS database name"
  type        = string
  default     = "finance_db"
}
