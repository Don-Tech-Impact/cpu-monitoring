subnet_prefix = "10.0.0.0/16"

ami_name_filter = {
    description = "Filter for Amazon Linux 2 AMI"
    name        = "amzn2-ami-hvm-*-x86_64-gp2"
    default     = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
    type        = string
}

# We can also work with lists
# availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
# can be used in main.tf like this:
# resource "aws_subnet" "custom_subnet" {   
#     vpc_id = aws_vpc.custom_default.id
#     cidr_block = "${var.subnet_prefix}.1.0/24"
#     availability_zone = var.availability_zones[0] # This will use the first availability zone in the list
#     map_public_ip_on_launch = true    
#     tags = {
#         Name = "custom-default-subnet"    
#     }


# we can also have list of objects for more complex configurations, for example:
# variable "subnets" {
#     description = "List of subnets to create"
#     type = list(object({
#         name = string
#         cidr_block = string
#         availability_zone = string
#     }))
#     default = [
#         {


# how to call this in main.tf:
# resource "aws_subnet" "custom_subnet" {
#     for_each = { for subnet in var.subnets : subnet.name => subnet }
#     vpc_id = aws_vpc.custom_default.id
#     cidr_block = each.value.cidr_block
#     availability_zone = each.value.availability_zone
#     map_public_ip_on_launch = true
#     tags = {
#         Name = each.value.name
#     }

## a siple object for subnet prefixes
# subnet_prefixes = [{ cidr_block = "10.0.0.0/24", name = "subnet-1" }, { cidr_block = "10.0.1.0/24", name = "subnet-2" }]

##Calling it inside the main.tf
# resource "aws_subnet" "custom_subnet" {
# cidr_block = var.subnet_prefixes[0].cidr_block
# availability_zone = "us-east-1a" 
# }

# for the name
# resource "aws_subnet" "custom_subnet" {
#     vpc_id = aws_vpc.custom_default.id
#     cidr_block = var.subnet_prefixes[0].cidr_block
#     availability_zone = "us-east-1a"
# tags = {
#     Name = var.subnet_prefixes[0].name    
# }