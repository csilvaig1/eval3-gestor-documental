# Variables del proyecto
# Los valores reales van en terraform.tfvars (que NO se sube al repositorio)

variable "prefijo" {
  description = "Prefijo para nombrar los recursos"
  type        = string
  default     = "chorombo"
}

variable "region" {
  description = "Region de Azure donde se despliega todo"
  type        = string
  default     = "eastus"
}

variable "usuario_admin" {
  description = "Usuario administrador de las maquinas virtuales"
  type        = string
  default     = "azureuser"
}

variable "ruta_clave_publica" {
  description = "Ruta a la clave publica SSH para acceder a las VMs"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "mi_ip" {
  description = "IP publica desde donde me conecto por SSH (formato x.x.x.x/32)"
  type        = string
}

variable "repo_app" {
  description = "URL del repositorio Git con el codigo de la aplicacion"
  type        = string
}

variable "clave_bd" {
  description = "Contrasena del usuario de PostgreSQL"
  type        = string
  sensitive   = true
}

variable "instancias_min" {
  description = "Cantidad minima de instancias de la aplicacion"
  type        = number
  default     = 2
}

variable "instancias_max" {
  description = "Cantidad maxima de instancias de la aplicacion"
  type        = number
  default     = 4
}
