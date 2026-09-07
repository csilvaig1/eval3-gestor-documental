# =============================================================================
# Infraestructura del Gestor Documental - Escuela G-733 Chorombo Bajo
# Evaluacion Unidad 3 - Arquitectura de Soluciones Cloud
# Alvaro Carrasco - IPSS
#
# Despliega en Azure:
#   - Red virtual con dos subredes (aplicacion y servicios)
#   - Scale Set con la aplicacion, detras de un balanceador de carga
#   - Regla de autoescalado por uso de CPU
#   - VM de servicios con PostgreSQL, Prometheus y Grafana
#   - Cuenta de almacenamiento para los documentos
# =============================================================================

terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
}

provider "azurerm" {
  features {}
}

# -----------------------------------------------------------------------------
# Grupo de recursos
# -----------------------------------------------------------------------------
resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.prefijo}-eval3"
  location = var.region

  tags = {
    proyecto   = "Gestor Documental VcM"
    asignatura = "Arquitectura de Soluciones Cloud"
    alumno     = "Alvaro Carrasco"
  }
}

# -----------------------------------------------------------------------------
# Red virtual y subredes
# -----------------------------------------------------------------------------
resource "azurerm_virtual_network" "vnet" {
  name                = "vnet-${var.prefijo}"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

# Subred donde viven las instancias de la aplicacion
resource "azurerm_subnet" "subnet_app" {
  name                 = "subnet-app"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Subred separada para la base de datos y el monitoreo
resource "azurerm_subnet" "subnet_servicios" {
  name                 = "subnet-servicios"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.0.2.0/24"]
}

# -----------------------------------------------------------------------------
# Grupos de seguridad de red (firewall a nivel de subred)
# -----------------------------------------------------------------------------
resource "azurerm_network_security_group" "nsg_app" {
  name                = "nsg-app"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  # El balanceador consulta el puerto 8000 de cada instancia
  security_rule {
    name                       = "permitir-http-desde-balanceador"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8000"
    source_address_prefix      = "AzureLoadBalancer"
    destination_address_prefix = "*"
  }

  # Trafico desde Internet que entra via el balanceador
  security_rule {
    name                       = "permitir-http-internet"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "8000"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  # Prometheus (en la VM de servicios) recolecta metricas de las instancias
  security_rule {
    name                       = "permitir-metricas-desde-vnet"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["9100", "8000"]
    source_address_prefix      = "10.0.2.0/24"
    destination_address_prefix = "*"
  }

  # SSH solo desde mi IP, no desde cualquier lugar
  security_rule {
    name                       = "permitir-ssh-solo-mi-ip"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.mi_ip
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_security_group" "nsg_servicios" {
  name                = "nsg-servicios"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  # PostgreSQL: solo accesible desde la subred de la aplicacion
  security_rule {
    name                       = "permitir-postgres-desde-app"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "5432"
    source_address_prefix      = "10.0.1.0/24"
    destination_address_prefix = "*"
  }

  # Grafana y Prometheus: solo desde mi IP para revisar los paneles
  security_rule {
    name                       = "permitir-monitoreo-mi-ip"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["3000", "9090"]
    source_address_prefix      = var.mi_ip
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "permitir-ssh-solo-mi-ip"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.mi_ip
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "asoc_app" {
  subnet_id                 = azurerm_subnet.subnet_app.id
  network_security_group_id = azurerm_network_security_group.nsg_app.id
}

resource "azurerm_subnet_network_security_group_association" "asoc_servicios" {
  subnet_id                 = azurerm_subnet.subnet_servicios.id
  network_security_group_id = azurerm_network_security_group.nsg_servicios.id
}

# -----------------------------------------------------------------------------
# Almacenamiento de los documentos (Azure Blob Storage)
# -----------------------------------------------------------------------------
resource "azurerm_storage_account" "almacenamiento" {
  name                     = "st${var.prefijo}docs"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Solo se aceptan conexiones cifradas (requisito ISO/IEC 27017)
  https_traffic_only_enabled = true
  min_tls_version            = "TLS1_2"
}

resource "azurerm_storage_container" "documentos" {
  name                  = "documentos"
  storage_account_name  = azurerm_storage_account.almacenamiento.name
  container_access_type = "private" # nunca publico: son datos de menores
}

# -----------------------------------------------------------------------------
# Balanceador de carga
# -----------------------------------------------------------------------------
resource "azurerm_public_ip" "ip_balanceador" {
  name                = "pip-balanceador"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_lb" "balanceador" {
  name                = "lb-${var.prefijo}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "Standard"

  frontend_ip_configuration {
    name                 = "frontend-publico"
    public_ip_address_id = azurerm_public_ip.ip_balanceador.id
  }
}

resource "azurerm_lb_backend_address_pool" "pool" {
  name            = "pool-instancias-app"
  loadbalancer_id = azurerm_lb.balanceador.id
}

# Health probe: si una instancia deja de responder en /health,
# el balanceador la saca automaticamente del pool
resource "azurerm_lb_probe" "probe" {
  name                = "probe-health"
  loadbalancer_id     = azurerm_lb.balanceador.id
  protocol            = "Http"
  port                = 8000
  request_path        = "/health"
  interval_in_seconds = 15
  number_of_probes    = 2
}

resource "azurerm_lb_rule" "regla" {
  name                           = "regla-http"
  loadbalancer_id                = azurerm_lb.balanceador.id
  protocol                       = "Tcp"
  frontend_port                  = 80
  backend_port                   = 8000
  frontend_ip_configuration_name = "frontend-publico"
  backend_address_pool_ids       = [azurerm_lb_backend_address_pool.pool.id]
  probe_id                       = azurerm_lb_probe.probe.id
}

# OJO: con un balanceador de SKU Standard, las maquinas del pool pierden la
# salida a Internet por defecto. Sin esta regla, cloud-init no puede hacer
# "apt install" ni "git clone" y las instancias arrancan sin la aplicacion.
resource "azurerm_lb_outbound_rule" "salida" {
  name                    = "regla-salida-internet"
  loadbalancer_id         = azurerm_lb.balanceador.id
  protocol                = "All"
  backend_address_pool_id = azurerm_lb_backend_address_pool.pool.id

  frontend_ip_configuration {
    name = "frontend-publico"
  }
}

# -----------------------------------------------------------------------------
# Scale Set con la aplicacion
# -----------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine_scale_set" "app" {
  name                = "vmss-${var.prefijo}-app"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Standard_B1s"
  instances           = var.instancias_min
  admin_username      = var.usuario_admin

  # Las instancias se reparten entre las zonas de disponibilidad 1 y 2,
  # de modo que la caida de una zona no deje el servicio abajo
  zones        = ["1", "2"]
  zone_balance = true
  upgrade_mode = "Manual"

  admin_ssh_key {
    username   = var.usuario_admin
    public_key = file(var.ruta_clave_publica)
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  os_disk {
    storage_account_type = "Standard_LRS"
    caching              = "ReadWrite"
  }

  network_interface {
    name    = "nic-app"
    primary = true

    ip_configuration {
      name                                   = "interno"
      primary                                = true
      subnet_id                              = azurerm_subnet.subnet_app.id
      load_balancer_backend_address_pool_ids = [azurerm_lb_backend_address_pool.pool.id]
    }
  }

  # Script de arranque que instala y levanta la aplicacion
  custom_data = base64encode(templatefile("${path.module}/cloud-init-app.yaml", {
    repo_app  = var.repo_app
    db_host   = azurerm_network_interface.nic_servicios.private_ip_address
    clave_bd  = var.clave_bd
    blob_conn = azurerm_storage_account.almacenamiento.primary_connection_string
  }))

  depends_on = [azurerm_network_interface.nic_servicios]
}

# -----------------------------------------------------------------------------
# Autoescalado: la métrica y el umbral que exige la rubrica
# -----------------------------------------------------------------------------
resource "azurerm_monitor_autoscale_setting" "autoescalado" {
  name                = "autoescalado-app"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  target_resource_id  = azurerm_linux_virtual_machine_scale_set.app.id

  profile {
    name = "perfil-por-cpu"

    capacity {
      default = var.instancias_min
      minimum = var.instancias_min
      maximum = var.instancias_max
    }

    # Escalar hacia arriba: CPU promedio sobre 70% durante 5 minutos
    rule {
      metric_trigger {
        metric_name        = "Percentage CPU"
        metric_resource_id = azurerm_linux_virtual_machine_scale_set.app.id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT5M"
        time_aggregation   = "Average"
        operator           = "GreaterThan"
        threshold          = 70
      }
      scale_action {
        direction = "Increase"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT5M"
      }
    }

    # Escalar hacia abajo: CPU promedio bajo 30% durante 10 minutos
    rule {
      metric_trigger {
        metric_name        = "Percentage CPU"
        metric_resource_id = azurerm_linux_virtual_machine_scale_set.app.id
        time_grain         = "PT1M"
        statistic          = "Average"
        time_window        = "PT10M"
        time_aggregation   = "Average"
        operator           = "LessThan"
        threshold          = 30
      }
      scale_action {
        direction = "Decrease"
        type      = "ChangeCount"
        value     = "1"
        cooldown  = "PT5M"
      }
    }
  }
}

# -----------------------------------------------------------------------------
# VM de servicios: PostgreSQL + Prometheus + Grafana
# -----------------------------------------------------------------------------
resource "azurerm_public_ip" "ip_servicios" {
  name                = "pip-servicios"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_interface" "nic_servicios" {
  name                = "nic-servicios"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name

  ip_configuration {
    name                          = "interno"
    subnet_id                     = azurerm_subnet.subnet_servicios.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.ip_servicios.id
  }
}

resource "azurerm_linux_virtual_machine" "servicios" {
  name                  = "vm-${var.prefijo}-servicios"
  resource_group_name   = azurerm_resource_group.rg.name
  location              = azurerm_resource_group.rg.location
  size                  = "Standard_B2s" # 2 vCPU / 4 GB: alcanza para BD + monitoreo
  admin_username        = var.usuario_admin
  network_interface_ids = [azurerm_network_interface.nic_servicios.id]

  admin_ssh_key {
    username   = var.usuario_admin
    public_key = file(var.ruta_clave_publica)
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  os_disk {
    storage_account_type = "Standard_LRS"
    caching              = "ReadWrite"
  }
}
