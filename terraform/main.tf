terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.92"
    }
  }

  required_version = ">= 1.2"
}

provider "aws" {
  region = "us-east-1"
}

data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

resource "aws_instance" "public_web_server" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = "t2.micro"
  subnet_id     = aws_subnet.custom_subnet.id
  vpc_security_group_ids = [aws_security_group.custom_default.id]


  associate_public_ip_address = true

  tags = {
    Name = "public_web-server-terraform"
  }

  user_data = <<-EOF
    #!/bin/bash
    apt-get update -y
    apt-get install -y nginx
    systemctl start nginx
    systemctl enable nginx
    echo "Hello, World from $(hostname -f)" | tee /var/www/html/index.html
  EOF
}

# resource "aws_instance" "public_web_server" {
#     ami          = data.aws_ami.ubuntu.id
#     instance_type = "t2.micro"
    
#     associated_public_ip_address = true
#     tags = {
#         Name = "public_web-server-terraform"
#     }

#     network_interface {
#         device_index         = 0
#         network_interface_id = aws_network_interface.web_server_eni.id
#     }
#     user_data = <<-EOF
#         #!/bin/bash
#         apt-get update -y
#         apt-get install -y apache2
#         systemctl start apache2
#         systemctl enable apache2
#         echo "Hello, World from $(hostname -f)" > /var/www/html/index.html
#     EOF
# }

resource "aws_vpc" "custom_default" {
    cidr_block = "10.0.0.0/16"
    tags = {
        Name = "custom-default-vpc"
    }
}

resource "aws_subnet" "custom_subnet" {
    vpc_id = aws_vpc.custom_default.id
    cidr_block = "10.0.1.0/24"
    availability_zone = "us-east-1a"
    map_public_ip_on_launch = true
    tags = {
        Name = "custom-default-subnet"
    }
}

resource "aws_internet_gateway" "custom_default" {
    vpc_id = aws_vpc.custom_default.id
    tags = {
        Name = "custom-default-igw"
    }
}

resource "aws_route_table" "custom_default" {
    vpc_id = aws_vpc.custom_default.id
    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.custom_default.id
    }
    # route {
    #     ipv6_cidr_block = "::/0"
    #     gateway_id      = aws_internet_gateway.custom_default.id
    # }
    tags = {
        Name = "custom-default-route-table"
    }
}

resource "aws_route_table_association" "custom_default" {
    subnet_id = aws_subnet.custom_subnet.id
    route_table_id = aws_route_table.custom_default.id
}

# resource "aws_nat_gateway" "custom_default" {
#     allocation_id = aws_eip.custom_default.id
#     subnet_id = aws_subnet.custom_default.id
#     tags = {
#         Name = "custom-default-nat-gateway"
#     }
  
# }

# resource "aws_network_interface" "web_server_eni" {
#     subnet_id = aws_subnet.custom_subnet.id
#     security_groups = [aws_security_group.custom_default.id]
    
#     tags = {
#         Name = "web-server-eni"
#     }
# }

resource "aws_eip" "custom_default" {
    domain = "vpc"
    tags = {
        Name = "custom-default-eip"
    }
}

# resource "aws_eip_association" "custom_default" {
#     allocation_id = aws_eip.custom_default.id
#     instance_id = aws_instance.public_web_server.id
#     # network_interface_id = aws_network_interface.web_server_eni.id
#     depends_on = [aws_internet_gateway.custom_default]
# }

resource "aws_security_group" "custom_default" {
    name = "custom_default_sg"
    description = "Allow SSH and HTTP inbound traffic"
    vpc_id = aws_vpc.custom_default.id

    ingress {
        description = "Allow ssh"
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        description = "Allow HTTPS traffic"
        from_port   = 443
        to_port     = 443
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        description = "Allow HTTP traffic"
        from_port   = 80
        to_port     = 80
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    egress {
        description = "Allow all outbound traffic"
        from_port   = 0
        to_port     = 0
        protocol    = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }
  
}


# resource "aws_instance" "app_server" {
#   ami           = data.aws_ami.ubuntu.id
#   instance_type = "t2.micro"

#   tags = {
#     Name = "public_web-server-terraform"
#   }

#   network_interface {
#     device_index         = 0
#     network_interface_id = aws_network_interface.web_server_eni.id
#   }

#   user_data = <<-EOF
#               #!/bin/bash
#               apt-get update -y
#               apt-get install -y nginx
#               systemctl start nginx
#               systemctl enable nginx
#               sudo echo "Hello, World from $(hostname -f)" > /var/www/html/index.html
#           EOF
# }

# resource "aws_vpc" "default" {
#   cidr_block = "10.0.0.0/16"
#   tags = {
#     Name = "default-vpc"
#   }
# }


# resource "aws_internet_gateway" "default" {
#   vpc_id = aws_vpc.default.id
#   tags = {
#     Name = "default-igw"
#   }
# }

# resource "aws_route_table" "default" {
#   vpc_id = aws_vpc.default.id
#   route {
#     cidr_block = "0.0.0.0/0"
#     gateway_id = aws_internet_gateway.default.id
#   }

#   route {
#     ipv6_cidr_block = "::/0"
#     gateway_id      = aws_internet_gateway.default.id
#   }
#   tags = {
#     Name = "default-route-table-for prod"
#   }

# }

# resource "aws_route_table_association" "default" {
#   subnet_id      = aws_subnet.default.id
#   route_table_id = aws_route_table.default.id
# }



# resource "aws_subnet" "default" {
#   vpc_id            = aws_vpc.default.id
#   cidr_block        = "10.0.2.0/24"
#   availability_zone = "us-east-1a"
#   tags = {
#     Name = "default-subnet"
#   }
# }

# resource "aws_security_group" "allow_ssh_and_web" {
#   name        = "allow_ssh_and_web"
#   description = "Allow SSH and HTTP inbound traffic"
#   vpc_id      = aws_vpc.default.id

#   ingress {
#     description = "Allow ssh"
#     from_port   = 22
#     to_port     = 22
#     protocol    = "tcp"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   ingress {
#     description = "Allow HTTPS traffic"
#     from_port   = 443
#     to_port     = 443
#     protocol    = "tcp"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   ingress {
#     description = "Allow HTTP traffic"
#     from_port   = 80
#     to_port     = 80
#     protocol    = "tcp"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   egress {
#     description = "Allow all outbound traffic"
#     from_port   = 0
#     to_port     = 0
#     protocol    = "-1"
#     cidr_blocks = ["0.0.0.0/0"]
#   }

#   ### Netwrok interface 
# }

# resource "aws_network_interface" "web_server_eni" {
#   subnet_id       = aws_subnet.default.id
#   security_groups = [aws_security_group.allow_ssh_and_web.id]
#   tags = {
#     Name = "app-server-eni"
#   }
# }

# resource "aws_eip" "web_server_eip" {
#   domain = "vpc"
#   tags = {
#     Name = "app-server-eip"
#   }
# }

# resource "aws_eip_association" "web_server_eip_assoc" {
#   allocation_id        = aws_eip.web_server_eip.id
#   network_interface_id = aws_network_interface.web_server_eni.id
#   depends_on           = [aws_internet_gateway.default]
# }